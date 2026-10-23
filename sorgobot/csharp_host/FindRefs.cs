using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Text.Json;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;

public static class FindRefs
{
    public static int Main()
    {
        try {
            using var request=JsonDocument.Parse(Console.In.ReadToEnd());var root=request.RootElement;
            var rejected=new List<string>();var references=new List<MetadataReference>();
            foreach(var path in root.GetProperty("paths").EnumerateArray().Select(p=>p.GetString()!).Distinct()) {
                try { references.Add(MetadataReference.CreateFromFile(path)); }
                catch(Exception error) { rejected.Add(Path.GetFileName(path)+": "+error.Message); }
            }
            var tree=CSharpSyntaxTree.ParseText(root.GetProperty("source").GetString()!);
            var host=CSharpSyntaxTree.ParseText(root.GetProperty("host").GetString()!);
            var compilation=CSharpCompilation.Create("ReferenceCheck",new[]{tree,host},references,new CSharpCompilationOptions(OutputKind.ConsoleApplication));
            var errors=compilation.GetDiagnostics().Where(d=>d.Severity==DiagnosticSeverity.Error).Select(d=>d.ToString()).Take(20).ToArray();
            var used=compilation.GetUsedAssemblyReferences().OfType<PortableExecutableReference>().Select(r=>r.FilePath).Where(p=>p!=null).Distinct().OrderBy(p=>p).ToArray();
            Console.Write(JsonSerializer.Serialize(new {references=used,diagnostics=errors,rejected}));return 0;
        }catch(Exception error){Console.Write(JsonSerializer.Serialize(new {error=error.Message}));return 1;}
    }
}
