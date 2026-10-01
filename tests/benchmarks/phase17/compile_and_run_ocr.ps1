param(
    [string]$ImagePath = "E:\Workspace\Active\AstraRun\tests\benchmarks\phase17\fixtures\test_ui.png"
)

$refs = @(
    "C:\Windows\System32\WinMetadata\Windows.Foundation.winmd",
    "C:\Windows\System32\WinMetadata\Windows.Storage.winmd",
    "C:\Windows\System32\WinMetadata\Windows.Graphics.winmd",
    "C:\Windows\System32\WinMetadata\Windows.Media.winmd",
    "System.Runtime.WindowsRuntime.dll"
)

$source = @"
using System;
using System.IO;
using System.Collections.Generic;
using System.Threading.Tasks;
using Windows.Graphics.Imaging;
using Windows.Media.Ocr;
using Windows.Storage;

public class WinRtOcr
{
    public static string RunOcr(string path)
    {
        var file = WindowsRuntimeSystemExtensions.AsTask(StorageFile.GetFileFromPathAsync(path)).GetAwaiter().GetResult();
        using (var stream = WindowsRuntimeSystemExtensions.AsTask(file.OpenAsync(FileAccessMode.Read)).GetAwaiter().GetResult())
        {
            var decoder = WindowsRuntimeSystemExtensions.AsTask(BitmapDecoder.CreateAsync(stream)).GetAwaiter().GetResult();
            var bitmap = WindowsRuntimeSystemExtensions.AsTask(decoder.GetSoftwareBitmapAsync()).GetAwaiter().GetResult();
            var engine = OcrEngine.TryCreateFromUserProfileLanguages();
            var result = WindowsRuntimeSystemExtensions.AsTask(engine.RecognizeAsync(bitmap)).GetAwaiter().GetResult();
            return result.Text;
        }
    }
}
"@

try {
    Add-Type -TypeDefinition $source -ReferencedAssemblies $refs
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $text = [WinRtOcr]::RunOcr($ImagePath)
    $sw.Stop()
    
    $out = @{
        status = "PASS"
        text = $text
        elapsed_ms = [Math]::Round($sw.Elapsed.TotalMilliseconds, 2)
    }
    $out | ConvertTo-Json
} catch {
    $err = @{
        status = "FAIL"
        error = $_.Exception.ToString()
    }
    $err | ConvertTo-Json
}
