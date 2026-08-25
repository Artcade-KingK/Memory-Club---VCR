<#
.SYNOPSIS
    Detecte et retire automatiquement les bandes noires (pillarbox / letterbox) des
    videos d'un dossier, via ffmpeg.

.DESCRIPTION
    Pour chaque video du dossier indique, le script analyse une portion de la video
    pour detecter la zone d'image reelle (sans bandes noires), puis recree une copie
    recadree dans un sous-dossier "Boxed". Les fichiers originaux ne sont JAMAIS
    modifies ni supprimes.

.USAGE
    .\BoxCutter.ps1 -Path "C:\chemin\vers\dossier"

    Si -Path est omis, utilise le dossier courant.

.PREREQUIS
    ffmpeg et ffprobe doivent etre installes et accessibles dans le PATH.
    Installation rapide : winget install --id Gyan.FFmpeg -e
    (ferme et rouvre PowerShell apres l'installation)
#>

param(
    [string]$Path = (Get-Location).Path
)

# --- Verifier ffmpeg / ffprobe ---
$ffmpegCmd = Get-Command ffmpeg -ErrorAction SilentlyContinue
$ffprobeCmd = Get-Command ffprobe -ErrorAction SilentlyContinue
if (-not $ffmpegCmd -or -not $ffprobeCmd) {
    Write-Host "ffmpeg / ffprobe introuvable(s) dans le PATH." -ForegroundColor Red
    Write-Host ""
    Write-Host "Installe-le avec :"
    Write-Host "    winget install --id Gyan.FFmpeg -e" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Ferme puis rouvre PowerShell apres l'installation, et relance ce script."
    exit 1
}

$extensions = @(".mp4", ".avi", ".mkv", ".mov")

if (-not (Test-Path $Path)) {
    Write-Host "Dossier introuvable : $Path" -ForegroundColor Red
    exit 1
}

$srcFolder = (Resolve-Path $Path).Path
$outFolder = Join-Path $srcFolder "Boxed"

if (-not (Test-Path $outFolder)) {
    New-Item -ItemType Directory -Path $outFolder | Out-Null
}

$videos = Get-ChildItem -Path $srcFolder -File | Where-Object { $extensions -contains $_.Extension.ToLower() }

if ($videos.Count -eq 0) {
    Write-Host "Aucune video trouvee dans $srcFolder"
    exit 0
}

Write-Host "$($videos.Count) video(s) trouvee(s) dans $srcFolder"
Write-Host "Sortie : $outFolder"
Write-Host ""

$tmpLog = Join-Path $env:TEMP "cropdetect_$([guid]::NewGuid().ToString('N')).log"
$i = 0

foreach ($video in $videos) {
    $i++
    $outFile = Join-Path $outFolder $video.Name

    Write-Host "[$i/$($videos.Count)] $($video.Name)"

    if (Test-Path $outFile) {
        Write-Host "  -> deja traite, ignore." -ForegroundColor DarkGray
        continue
    }

    # Resolution d'origine
    $dims = & ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 "$($video.FullName)" 2>$null
    if (-not $dims) {
        Write-Host "  -> impossible de lire la video, ignoree." -ForegroundColor Red
        continue
    }
    $parts = $dims.Trim().Split(",")
    $origW = [int]$parts[0]
    $origH = [int]$parts[1]

    # Duree (pour choisir un point d'analyse pas au tout debut de la video)
    $durStr = & ffprobe -v error -show_entries format=duration -of csv=p=0 "$($video.FullName)" 2>$null
    $duration = 0
    [double]::TryParse(
        $durStr,
        [System.Globalization.NumberStyles]::Float,
        [System.Globalization.CultureInfo]::InvariantCulture,
        [ref]$duration
    ) | Out-Null

    $startAt = 0
    if ($duration -gt 30) { $startAt = [math]::Floor($duration * 0.1) }
    $sampleLen = 20
    if ($duration -gt 0 -and ($startAt + $sampleLen) -gt $duration) {
        $sampleLen = [math]::Max(1, [math]::Floor($duration - $startAt))
    }

    # Detection des bandes noires : on ecrit le log ffmpeg dans un fichier temporaire
    # (plus fiable que de capturer stderr directement en PowerShell)
    & ffmpeg -hide_banner -ss $startAt -i "$($video.FullName)" -t $sampleLen -vf "cropdetect=limit=24:round=2:reset=0" -f null NUL 2> $tmpLog

    $cropW = $null; $cropH = $null; $cropX = $null; $cropY = $null
    Get-Content $tmpLog | ForEach-Object {
        if ($_ -match "crop=(\d+):(\d+):(\d+):(\d+)") {
            $cropW = [int]$Matches[1]
            $cropH = [int]$Matches[2]
            $cropX = [int]$Matches[3]
            $cropY = [int]$Matches[4]
        }
    }

    if (-not $cropW -or ($cropW -ge $origW -and $cropH -ge $origH)) {
        Write-Host "  -> pas de bandes noires detectees, copie telle quelle." -ForegroundColor DarkGray
        Copy-Item $video.FullName $outFile
        continue
    }

    Write-Host "  -> bandes noires detectees (${origW}x${origH} -> ${cropW}x${cropH}), recadrage..." -ForegroundColor Green

    & ffmpeg -hide_banner -loglevel error -stats -y -i "$($video.FullName)" `
        -vf "crop=${cropW}:${cropH}:${cropX}:${cropY}" `
        -c:v libx264 -crf 18 -preset medium -c:a copy -movflags +faststart `
        "$outFile"

    if (Test-Path $outFile) {
        Write-Host "  -> termine." -ForegroundColor Green
    } else {
        Write-Host "  -> echec de l'encodage." -ForegroundColor Red
    }
}

Remove-Item $tmpLog -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Termine. Videos recadrees dans : $outFolder" -ForegroundColor Cyan
