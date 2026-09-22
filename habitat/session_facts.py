"""Minimal per-request configuration observations; never a grant or health verdict."""
import platform
import time


def build(request_id, context_entries, orientation_count, commit=None):
    return {
        'schema_version': 1,
        'source': 'local_server_configuration_at_request',
        'request_id': request_id,
        'observed_at_unix': int(time.time()),
        'launcher_reported_commit': commit,
        'os_family': platform.system(),
        'inference_configuration': 'local_subprocess_on_this_host',
        'external_model_calls': 'disabled_for_this_backend',
        'model_tools': 'none_provided',
        'live_habitat_access': 'not_provided_through_model_interface',
        'context_entries_supplied': context_entries,
        'historical_orientation_notes_supplied': orientation_count,
        'persistent_personal_memory_retrieval': 'not_enabled_in_this_session',
        'authority': 'not_conferred_by_this_snapshot',
        'unknowns': ['current_hardware_health', 'other_processes', 'whole_habitat_state'],
    }
