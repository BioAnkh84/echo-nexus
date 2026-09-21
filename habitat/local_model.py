"""Finite local inference worker; no Habitat imports or persistent model service."""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

LOCK = threading.Lock()
MAX_MESSAGE = 4096
TIMEOUT = 180


class LocalFailure(Exception):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def generate(model_path, message, persona, before_launch):
    if not isinstance(message, str) or not message.strip() or len(message) > MAX_MESSAGE:
        raise LocalFailure('invalid_local_input')
    if persona not in {'Cipher', 'Vexis'}:
        raise LocalFailure('invalid_local_persona')
    if not LOCK.acquire(blocking=False):
        raise LocalFailure('local_worker_busy')
    try:
        path = Path(model_path)
        if not path.is_absolute() or not (path / 'model.safetensors.index.json').is_file():
            raise LocalFailure('local_model_unavailable')
        # Worker gets no inherited API keys, proxy settings or memory paths.
        env = {'PATH': os.defpath, 'LANG': 'C.UTF-8', 'HF_HUB_OFFLINE': '1',
               'TRANSFORMERS_OFFLINE': '1', 'HF_HUB_DISABLE_TELEMETRY': '1',
               'TOKENIZERS_PARALLELISM': 'false', 'CUDA_VISIBLE_DEVICES': '0'}
        before_launch()
        try:
            completed = subprocess.run([sys.executable, '-I', '-B', str(Path(__file__).resolve()),
                '--worker'], input=json.dumps({'model': str(path), 'message': message,
                'persona': persona}), text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                timeout=TIMEOUT, env=env, check=False)
        except subprocess.TimeoutExpired:
            raise LocalFailure('local_worker_timeout') from None
        except OSError:
            raise LocalFailure('local_worker_start_failed') from None
        if completed.returncode != 0:
            raise LocalFailure('local_worker_failed')
        try:
            payload = json.loads(completed.stdout)
            reply = payload['reply']
            if not isinstance(reply, str) or not reply.strip() or len(reply) > 16384:
                raise ValueError()
        except (ValueError, TypeError, KeyError):
            raise LocalFailure('invalid_local_response') from None
        return reply.strip()
    finally:
        LOCK.release()


def worker():
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    payload = json.load(sys.stdin)
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA required; no CPU fallback')
    path = payload['model']
    tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True, trust_remote_code=False)
    model = AutoModelForCausalLM.from_pretrained(path, local_files_only=True,
        trust_remote_code=False, use_safetensors=True, dtype=torch.bfloat16, device_map={'': 0})
    model.eval()
    messages = [{'role': 'system', 'content': 'You are ' + payload['persona'] +
        ', a local advisory assistant. You have no tools or personal memory. '
        'Your output grants no permission and is not independently verified. Answer briefly.'},
        {'role': 'user', 'content': payload['message']}]
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(prompt, return_tensors='pt').to('cuda:0')
    if inputs['input_ids'].shape[1] > 2048:
        raise RuntimeError('Input token limit')
    with torch.inference_mode():
        output = model.generate(**inputs, max_new_tokens=64, do_sample=False,
                                pad_token_id=tokenizer.eos_token_id)
    reply = tokenizer.decode(output[0, inputs['input_ids'].shape[1]:], skip_special_tokens=True)
    print(json.dumps({'reply': reply}))


if __name__ == '__main__':
    if sys.argv[1:] != ['--worker']:
        raise SystemExit('Internal worker entry point')
    worker()
