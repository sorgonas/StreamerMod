using System;
using System.Text.Json;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis;
public static class FormatCode
{
    public static int Main()
    {
        using var request=JsonDocument.Parse(Console.In.ReadToEnd());
        var root=request.RootElement;
        var tree=CSharpSyntaxTree.ParseText(root.GetProperty("code").GetString()!);
        var indent=new string(' ',root.GetProperty("indent").GetInt32());
        var code=tree.GetRoot().NormalizeWhitespace(indent,"\n",false).ToFullString();
        Console.Write(JsonSerializer.Serialize(new { code=code+"\n" }));
        return 0;
    }
}
