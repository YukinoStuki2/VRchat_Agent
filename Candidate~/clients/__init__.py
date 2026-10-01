"""Explicitly enabled standalone plugin. Import/register creates no listener."""
def register(ctx):
    from .hermes_gateway import GatewayPlugin
    return GatewayPlugin(ctx)
