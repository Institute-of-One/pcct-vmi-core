param([string]$OutputDir = "$PSScriptRoot\output")
$ErrorActionPreference = 'Stop'
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
$word.Options.Pagination = $false
try {
    foreach ($name in @('manuscript', 'title_page')) {
        $source = [IO.Path]::GetFullPath((Join-Path $OutputDir "$name.docx"))
        $pdf = [IO.Path]::GetFullPath((Join-Path $OutputDir "$name.pdf"))
        $doc = $word.Documents.Open($source, $false, $true)
        try { $doc.ExportAsFixedFormat($pdf, 17) } finally { $doc.Close(0) }
        Write-Output "Exported $pdf"
    }
} finally {
    $word.Quit()
    [void][Runtime.InteropServices.Marshal]::ReleaseComObject($word)
}
