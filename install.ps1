# LumiRipple installer for Windows 10/11, for the current user, without administrator rights.
#   irm https://raw.githubusercontent.com/OWNER/lumiripple/main/install.ps1 | iex
# Remove it again:  & ([scriptblock]::Create((irm .../install.ps1))) -Uninstall
param([switch]$Uninstall)

function Install-LumiRipple([bool]$Remove) {
    $ErrorActionPreference = 'Stop'
    $repo = if ($env:LUMIRIPPLE_REPO) { $env:LUMIRIPPLE_REPO } else { 'https://github.com/OWNER/lumiripple' }
    $ref = if ($env:LUMIRIPPLE_REF) { $env:LUMIRIPPLE_REF } else { 'main' }
    $base = Join-Path $env:LOCALAPPDATA 'LumiRipple'
    $startup = Join-Path ([Environment]::GetFolderPath('Startup')) 'LumiRipple.lnk'
    $menu = Join-Path ([Environment]::GetFolderPath('Programs')) 'LumiRipple.lnk'

    Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" | Where-Object { $_.CommandLine -like '*-m lumiripple run*' } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
    if ($Remove) {
        Remove-Item $startup, $menu -ErrorAction SilentlyContinue
        Remove-Item $base -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host 'LumiRipple is removed. Your settings were kept in %APPDATA%\lumiripple.'
        return
    }

    $python = $null
    foreach ($c in @(@('py', '-3'), @('python', ''))) {
        if (Get-Command $c[0] -ErrorAction SilentlyContinue) {
            $more = @($c | Select-Object -Skip 1 | Where-Object { $_ })
            & $c[0] @more -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>$null
            if ($LASTEXITCODE -eq 0) { $python = $c[0]; break }
        }
    }
    if (-not $python) { throw 'Python 3.10 or newer is needed. Install it with:  winget install Python.Python.3.12   and run this again in a new window.' }

    $here = if ($PSScriptRoot) { $PSScriptRoot } else { '' }
    if ($here -and (Test-Path (Join-Path $here 'lumiripple/__main__.py'))) { $src = $here }
    else {
        if ($repo -like '*/OWNER/*') { throw 'This copy has no download address yet; run it from a checkout or set LUMIRIPPLE_REPO.' }
        $tmp = Join-Path $env:TEMP ('lumiripple-' + [guid]::NewGuid())
        New-Item -ItemType Directory $tmp | Out-Null
        Write-Host "Downloading LumiRipple ($ref)"
        Invoke-WebRequest "$repo/archive/$ref.zip" -OutFile "$tmp\a.zip" -UseBasicParsing
        Expand-Archive "$tmp\a.zip" $tmp
        $src = (Get-ChildItem $tmp -Directory | Select-Object -First 1).FullName
        if (-not (Test-Path (Join-Path $src 'lumiripple/__main__.py'))) { throw 'The download is incomplete.' }
    }

    Write-Host "Installing to $base"
    New-Item -ItemType Directory -Force "$base\app" | Out-Null
    Remove-Item "$base\app\lumiripple" -Recurse -Force -ErrorAction SilentlyContinue
    Copy-Item (Join-Path $src 'lumiripple') "$base\app" -Recurse
    if (-not (Test-Path "$base\venv\Scripts\python.exe")) { & $python @more -m venv "$base\venv" }
    & "$base\venv\Scripts\python.exe" -m pip install -q --upgrade pip
    & "$base\venv\Scripts\python.exe" -m pip install -q pynput psutil numpy soundcard
    if ($LASTEXITCODE -ne 0) { throw 'Installing the Python packages failed.' }

    $shell = New-Object -ComObject WScript.Shell
    foreach ($x in @(@($startup, 'run'), @($menu, 'open'))) {
        $l = $shell.CreateShortcut($x[0])
        $l.TargetPath = "$base\venv\Scripts\pythonw.exe"
        $l.Arguments = "-m lumiripple $($x[1])"
        $l.WorkingDirectory = "$base\app"
        $l.Save()
    }
    Start-Process "$base\venv\Scripts\pythonw.exe" '-m lumiripple run' -WorkingDirectory "$base\app"
    Write-Host 'Done. Start the OpenRGB SDK server (OpenRGB > SDK Server > Start), then open LumiRipple from the start menu.'
}
Install-LumiRipple $Uninstall.IsPresent
