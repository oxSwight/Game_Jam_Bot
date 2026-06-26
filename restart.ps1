# Перезапуск Game Jam бота.
# Останавливает все запущенные экземпляры и запускает свежий с текущим .env.
Set-Location -Path $PSScriptRoot

Write-Host "==> Останавливаю запущенные экземпляры бота..." -ForegroundColor Yellow
$procs = Get-CimInstance Win32_Process -Filter "Name like '%python%'" |
    Where-Object { $_.CommandLine -like '*app.main*' }
if ($procs) {
    $procs | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force
        Write-Host "    остановлен PID $($_.ProcessId)"
    }
    Start-Sleep -Milliseconds 800
} else {
    Write-Host "    запущенных экземпляров не найдено"
}

# Снять файл-блокировку на случай, если процесс умер некорректно
Remove-Item ".bot.lock" -Force -ErrorAction SilentlyContinue

Write-Host "==> Запускаю бота (это окно показывает логи; закрой его, чтобы остановить)..." -ForegroundColor Green
& ".\.venv\Scripts\python.exe" -m app.main

Write-Host "`n==> Бот остановлен. Нажми любую клавишу, чтобы закрыть окно." -ForegroundColor Yellow
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
