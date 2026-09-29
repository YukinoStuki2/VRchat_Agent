// Re-run EVERY original AdapterCases assertion unchanged with a source-matched
// native success fixture instead of historical {fixture_only:true} (not native data).
// Original AdapterTests remains runnable and its incompatibility is retained.
using System.Reflection;
using MCPForUnity.Editor.Helpers;
using MCPForUnity.Editor.Tools;
internal static class FixAdapterEntry
{
    static int Main()
    {
        CommandRegistry.Implementation = (c,p) => new SuccessResponse("fixture material info",
            new { material="fixture material", shader="fixture shader", properties=new object[0] });
        return (int)typeof(AdapterCases).GetMethod("Main", BindingFlags.NonPublic|BindingFlags.Static).Invoke(null,null);
    }
}
