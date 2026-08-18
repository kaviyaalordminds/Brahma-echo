$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut('C:\Users\Kaviyaa\Desktop\Brahma Echo.lnk')
$Shortcut.TargetPath = 'C:\Users\Kaviyaa\AppData\Local\Programs\Python\Python311\python.exe'
$Shortcut.Arguments = '"C:\xampp\htdocs\Lordminds\Brahma-Echo\main.py"'
$Shortcut.WorkingDirectory = 'C:\xampp\htdocs\Lordminds\Brahma-Echo'
$Shortcut.WindowStyle = 7
$Shortcut.Description = 'Launch Brahma Echo'
if ('C:\xampp\htdocs\Lordminds\Brahma-Echo\assets\Brahma_Lite_Logo.ico') { $Shortcut.IconLocation = 'C:\xampp\htdocs\Lordminds\Brahma-Echo\assets\Brahma_Lite_Logo.ico,0' }
$Shortcut.Save()