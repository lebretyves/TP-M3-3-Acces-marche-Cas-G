param([switch]$SelfTest)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
$appRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $appRoot '.venv\Scripts\python.exe'
$helper = Join-Path $PSScriptRoot 'show_test_access.py'
$accounts = @('u-alice','c-lina','e-atelier','t-support','s-securite','s-approbateur')
$form = New-Object System.Windows.Forms.Form
$form.Text = 'SKELIVIA - Acces au banc local'
$form.ClientSize = New-Object System.Drawing.Size(540,430)
$form.StartPosition = 'CenterScreen'
$form.Font = New-Object System.Drawing.Font('Segoe UI',11)
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
function Label($text,$x,$y,$width,$height) {
    $label=New-Object System.Windows.Forms.Label
    $label.Text=$text; $label.SetBounds($x,$y,$width,$height)
    $form.Controls.Add($label); return $label
}
$title=Label 'Connexion SKELIVIA' 24 18 480 30
$title.Font=New-Object System.Drawing.Font('Segoe UI',16,[System.Drawing.FontStyle]::Bold)
$null=Label '1. Identifiant du compte' 24 60 480 25
$choice=New-Object System.Windows.Forms.ComboBox
$choice.DropDownStyle='DropDownList'; $choice.SetBounds(24,88,490,32)
$choice.Items.AddRange($accounts); $form.Controls.Add($choice)
$null=Label '2. Mot de passe' 24 136 300 25
$password=New-Object System.Windows.Forms.TextBox
$password.SetBounds(24,164,350,30); $password.ReadOnly=$true; $password.UseSystemPasswordChar=$true
$form.Controls.Add($password)
$copyPassword=New-Object System.Windows.Forms.Button
$copyPassword.Text='Copier'; $copyPassword.SetBounds(386,161,128,36); $form.Controls.Add($copyPassword)
$copyPassword.Add_Click({ if ($password.Text) { [System.Windows.Forms.Clipboard]::SetText($password.Text); $notice.Text='Mot de passe copie : collez-le dans la page de connexion.' } })
$null=Label '3. One-time code : uniquement ces 6 chiffres' 24 215 490 28
$code=Label '------' 24 247 280 48
$code.Font=New-Object System.Drawing.Font('Consolas',28,[System.Drawing.FontStyle]::Bold)
$copyCode=New-Object System.Windows.Forms.Button
$copyCode.Text='Copier le code'; $copyCode.SetBounds(350,250,164,42); $form.Controls.Add($copyCode)
$countdown=Label '' 24 302 490 26
$notice=Label 'Choisissez le meme compte que sur la page de connexion.' 24 338 490 48
$null=Label 'Recette locale - https://localhost:8443' 24 397 490 26
$script:counter=-1; $script:currentAccount=''
function Refresh-Code {
    $seconds=[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    $counter=[math]::Floor($seconds / 30)
    $left=30-($seconds % 30)
    $selected=[string]$choice.SelectedItem
    if (-not $selected) { return }
    if ($counter -ne $script:counter -or $selected -ne $script:currentAccount) {
        try {
            $password.Text=[IO.File]::ReadAllText((Join-Path $appRoot ('.runtime\infra\secrets\login_'+$selected))).Trim()
            $value=(& $python $helper --code $selected 2>$null | Out-String).Trim()
            if ($LASTEXITCODE -ne 0 -or $value -notmatch '^\d{6}$') { throw 'Code inaccessible' }
            $code.Text=$value; $script:counter=$counter; $script:currentAccount=$selected
        } catch {
            $code.Text='------'; $copyCode.Enabled=$false; $notice.Text='Acces indisponibles pour ce compte. Verifiez les fichiers de recette.'; return
        }
    }
    $countdown.Text='Code valable encore '+$left+' secondes. Renouvellement automatique.'
    $copyCode.Enabled=($left -gt 5)
    if ($left -le 5) { $countdown.Text='Attendez '+$left+' secondes : un nouveau code arrive.' }
}
$copyCode.Add_Click({
    Refresh-Code
    if ($copyCode.Enabled -and $code.Text -match '^\d{6}$') {
        [System.Windows.Forms.Clipboard]::SetText($code.Text)
        $notice.Text='Code copie. Collez-le dans One-time code et validez sans attendre.'
    }
})
$choice.Add_SelectedIndexChanged({ $notice.Text='Identifiant a saisir : '+$choice.SelectedItem; Refresh-Code })
$timer=New-Object System.Windows.Forms.Timer
$timer.Interval=250; $timer.Add_Tick({ Refresh-Code })
$form.Add_Shown({ $choice.SelectedIndex=0; $timer.Start() })
$form.Add_FormClosed({ $timer.Stop(); $timer.Dispose() })
if ($SelfTest) {
    $check=New-Object System.Windows.Forms.Timer; $check.Interval=1200
    $check.Add_Tick({
        $script:selfTestPassed=($code.Text -match '^\d{6}$')
        $check.Stop(); $form.Close()
    })
    $check.Start()
}
[void]$form.ShowDialog()
$form.Dispose()
if ($SelfTest) {
    Write-Output ('WindowReady=True; CodeSixDigits='+$script:selfTestPassed+'; AccountCount='+$accounts.Count)
    if (-not $script:selfTestPassed) { exit 1 }
}
