param(
    [Parameter(Mandatory = $true)][string]$Pptx,
    [Parameter(Mandatory = $true)][string]$OutDir,
    [int]$Width = 1600
)
# Renders every slide of a .pptx to PNG via PowerPoint COM (read-only, no window).
New-Item -ItemType Directory -Force $OutDir | Out-Null
$app = New-Object -ComObject PowerPoint.Application
try {
    # Open(FileName, ReadOnly, Untitled, WithWindow)
    $pres = $app.Presentations.Open($Pptx, -1, 0, 0)
    try {
        $h = [int]($Width * $pres.PageSetup.SlideHeight / $pres.PageSetup.SlideWidth)
        $i = 0
        foreach ($sl in $pres.Slides) {
            $i++
            $out = Join-Path $OutDir ("slide{0:D2}.png" -f $i)
            $sl.Export($out, "PNG", $Width, $h)
        }
        Write-Output "rendered $i slides to $OutDir"
    }
    finally { $pres.Close() }
}
finally {
    $app.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($app) | Out-Null
}
