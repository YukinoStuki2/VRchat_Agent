"""Uninstalled host-side new-conversation scope. Import starts nothing."""
import asyncio
import secrets
import json
from contextlib import asynccontextmanager
from hermes_binding import bind


@asynccontextmanager
async def conversation(peer, *, include, options):
    """Own one new agent and native peer; no live-agent replacement or model call."""
    from tools.registry import registry
    from run_agent import AIAgent
    from model_tools import get_tool_definitions
    identity = 'vrc-' + secrets.token_hex(24)
    binding = await bind(peer, registry, conversation_id=identity, include=include)
    agent = None
    worker = None
    try:
        if type(options) is not dict or {'session_id','enabled_toolsets','disabled_toolsets','prefill_messages'} & options.keys():
            raise ValueError('candidate_construction_options')
        options = options.copy()
        names = [item['function']['name'] for item in binding.snapshot()]
        toolset = registry.get_entry(names[0]).toolset
        expected = json.loads(json.dumps(get_tool_definitions(enabled_toolsets=[toolset],quiet_mode=True)))
        def close_owned(instance):
            instance.session_id = identity
            instance.close()

        def construct():
            # Retain ownership even if native __init__ fails partway through.
            instance = AIAgent.__new__(AIAgent)
            instance.session_id = identity  # close() must never see an empty/shared ID.
            try:
                AIAgent.__init__(instance, **options,
                    session_id=identity, enabled_toolsets=[toolset])
                return instance
            except BaseException:
                try:
                    close_owned(instance)
                finally:
                    raise RuntimeError('candidate_construction_failed') from None
        worker = asyncio.create_task(asyncio.to_thread(construct))
        agent = await asyncio.shield(worker)
        if (agent.session_id != identity or agent.enabled_toolsets != [toolset]
                or agent.valid_tool_names != {t['function']['name'] for t in expected}
                or agent.tools != expected):
            raise RuntimeError('candidate_construction_mismatch')
        agent.tools = json.loads(json.dumps(agent.tools))  # Before the first turn only.
        yield agent
    finally:
        async def finish():
            try:
                await binding.close()
            finally:
                if worker is not None:
                    try:
                        instance = await worker
                    except BaseException:
                        pass  # Failed constructors already closed their partial object.
                    else:
                        await asyncio.to_thread(close_owned, instance)
        cleanup = asyncio.create_task(finish())
        cancelled = None
        while not cleanup.done():
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError as exc:
                cancelled = exc
        cleanup.result()
        if cancelled is not None:
            raise cancelled
