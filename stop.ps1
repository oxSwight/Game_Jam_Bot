# Останавливает все запущенные экземпляры Game Jam бота.
Set-Location -Path $PSScriptRoot

$procs = Get-CimInstance Win32_Process -Filter "Name like '%python%'" |
    Where-Object { $_.CommandLine -like '*app.main*' }
if ($procs) {
    $procs | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force
        Write-Host "Остановлен PID $($_.ProcessId)" -ForegroundColor Yellow
    }
} else {
    Write-Host "Запущенных экземпляров не найдено." -ForegroundColor Green
}
Remove-Item ".bot.lock" -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1
