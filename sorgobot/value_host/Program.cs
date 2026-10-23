using System.Globalization;
using org.mariuszgromada.math.mxparser;
using System.Numerics;
using System.Text.Json;
using System.Text.RegularExpressions;

// The library retains its complete upstream dual license. This mode does not
// grant a license; users must satisfy the terms before selecting commercial use.
string licenseMode=Environment.GetEnvironmentVariable("STREAMERMOD_MXPARSER_LICENSE_MODE") ?? "noncommercial";
bool licenseConfirmed=licenseMode switch {
 "noncommercial" => License.iConfirmNonCommercialUse("StreamerMod non-commercial use; upstream dual-license terms apply"),
 "commercial" => License.iConfirmCommercialUse("StreamerMod commercial use selected by a separately licensed user"),
 _ => throw new InvalidOperationException("Unknown mXparser license mode")
};
if(!licenseConfirmed) throw new InvalidOperationException("mXparser license confirmation failed");

// Fixed formatting and mathematical expressions only; no user C#, files or RPC.
while (Console.ReadLine() is string line) {
 try {
  using var doc=JsonDocument.Parse(line);var root=doc.RootElement;
  string kind=root.GetProperty("kind").GetString()!, text=root.GetProperty("value").GetString()!, format=root.GetProperty("format").GetString()!;
  if(text.Length>16000 || format.Length>512)throw new FormatException("Wert oder Format zu lang");
  var precision=Regex.Match(format,@"^[A-Za-z](\d+)$");
  if(precision.Success && (precision.Groups[1].Value.Length>4 || int.Parse(precision.Groups[1].Value)>1000))throw new FormatException("Formatpräzision zu groß");
  string? cultureName=root.TryGetProperty("culture",out var c)?c.GetString():null;
  var culture=cultureName is null?CultureInfo.CurrentCulture:CultureInfo.GetCultureInfo(cultureName);
  if(kind=="math") {
   if(text.Length>1000)throw new FormatException("Math-Ausdruck zu lang");
   var expression=new Expression(text);
   bool valid=expression.checkSyntax();
   double number=valid?expression.calculate():double.NaN;
   bool strict=root.TryGetProperty("strict",out var strictValue) && strictValue.GetBoolean();
   if(strict && (!valid || !double.IsFinite(number)))throw new FormatException("Ungültiger oder nicht endlicher Math-Ausdruck");
   Console.WriteLine(JsonSerializer.Serialize(new {result=number.ToString(format,culture)}));
   continue;
  }
  object value=kind switch {
   "integer"=>ReadInteger(text),
   "float"=>double.Parse(text,CultureInfo.InvariantCulture),
   "decimal"=>decimal.Parse(text,NumberStyles.Float,CultureInfo.InvariantCulture),
   "date"=>DateTime.Parse(text,CultureInfo.InvariantCulture,DateTimeStyles.RoundtripKind),
   "offset"=>DateTimeOffset.Parse(text,CultureInfo.InvariantCulture,DateTimeStyles.None),
   "bool"=>bool.Parse(text),
   _=>text
  };
  string result=value is IFormattable typed?typed.ToString(format,culture)??"":value.ToString()??"";
  if(result.Length>64000)throw new FormatException("Formatierte Ausgabe zu lang");
  Console.WriteLine(JsonSerializer.Serialize(new {result}));
 } catch(Exception ex) {Console.WriteLine(JsonSerializer.Serialize(new {error=ex.GetType().Name,message=ex.Message}));}
}
static object ReadInteger(string text) {
 var value=BigInteger.Parse(text,CultureInfo.InvariantCulture);
 if(value>=int.MinValue && value<=int.MaxValue)return (int)value;
 if(value>=long.MinValue && value<=long.MaxValue)return (long)value;
 return value;
}
