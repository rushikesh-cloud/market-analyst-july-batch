$ErrorActionPreference = 'Stop'
$devExitCode = 1

Push-Location -LiteralPath $PSScriptRoot
try {
    & npm.cmd run dev
    $devExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}

exit $devExitCode
