using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
// Parse using Unity 2022.3's C# language level. This is NOT Unity type checking.
if (args.Length != 1 || !Directory.Exists(args[0])) throw new ArgumentException("Pass package Editor source directory.");
var paths = Directory.GetFiles(args[0], "*.cs", SearchOption.AllDirectories).OrderBy(x => x).ToArray();
if (paths.Length == 0) throw new Exception("No production C# files to check.");
int errors = 0;
foreach (var path in paths)
{
    var tree = CSharpSyntaxTree.ParseText(File.ReadAllText(path), new CSharpParseOptions(LanguageVersion.CSharp9), path);
    foreach (var d in tree.GetDiagnostics().Where(d => d.Severity == DiagnosticSeverity.Error)) { Console.WriteLine(d); errors++; }
}
Console.WriteLine($"C#9 syntax: {paths.Length} files, {errors} errors. Unity API/type/Editor execution NOT verified by this check.");
return errors == 0 ? 0 : 1;
