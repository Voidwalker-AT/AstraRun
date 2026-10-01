param(
    [string]$ImagePath = "E:\Workspace\Active\AstraRun\tests\benchmarks\phase17\fixtures\test_ui.png"
)

$swTotal = [System.Diagnostics.Stopwatch]::StartNew()

Add-Type -AssemblyName System.Runtime.WindowsRuntime
[Windows.Media.Ocr.OcrEngine, Windows.Media.Ocr, ContentType = WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType = WindowsRuntime] | Out-Null
[Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime] | Out-Null

function Await-Task($winRtOp) {
    $asTaskMethod = [System.WindowsRuntimeSystemExtensions].GetMethods() | 
        Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.IsGenericMethod } | 
        Select-Object -First 1
    
    # Check if generic or non-generic
    if ($winRtOp.GetType().GetInterfaces() | Where-Object { $_.Name -like 'IAsyncOperation*' }) {
        $interface = $winRtOp.GetType().GetInterfaces() | Where-Object { $_.Name -like 'IAsyncOperation*' } | Select-Object -First 1
        $returnType = $interface.GetGenericArguments()[0]
        $genericMethod = $asTaskMethod.MakeGenericMethod($returnType)
        $task = $genericMethod.Invoke($null, @($winRtOp))
        $task.Wait()
        return $task.Result
    }
}

$fileOp = [Windows.Storage.StorageFile]::GetFileFromPathAsync($ImagePath)
$file = Await-Task $fileOp

$streamOp = $file.OpenAsync([Windows.Storage.FileAccessMode]::Read)
$stream = Await-Task $streamOp

$decoderOp = [Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)
$decoder = Await-Task $decoderOp

$bitmapOp = $decoder.GetSoftwareBitmapAsync()
$bitmap = Await-Task $bitmapOp

$swInfer = [System.Diagnostics.Stopwatch]::StartNew()
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
$ocrOp = $engine.RecognizeAsync($bitmap)
$result = Await-Task $ocrOp
$swInfer.Stop()
$swTotal.Stop()

$lines = @()
foreach ($l in $result.Lines) {
    $words = @()
    foreach ($w in $l.Words) {
        $words += @{
            text = $w.Text
            x = [int]$w.BoundingRect.X
            y = [int]$w.BoundingRect.Y
            width = [int]$w.BoundingRect.Width
            height = [int]$w.BoundingRect.Height
        }
    }
    $lines += @{
        text = $l.Text
        words = $words
    }
}

$output = @{
    full_text = $result.Text
    line_count = $result.Lines.Count
    lines = $lines
    inference_time_ms = [Math]::Round($swInfer.Elapsed.TotalMilliseconds, 2)
    total_time_ms = [Math]::Round($swTotal.Elapsed.TotalMilliseconds, 2)
    language = $engine.RecognizerLanguage.LanguageTag
}

$output | ConvertTo-Json -Depth 5
