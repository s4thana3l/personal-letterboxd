# w Entra na pasta do projeto independentemente do diretório atual.
Set-Location $PSScriptRoot

# w Cria o ambiente virtual caso ele ainda não exista.
if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    python -m venv .venv
    if (-not $?) {
        throw "Não foi possível criar o ambiente virtual."
    }
}

# w Instala as dependências necessárias para executar a aplicação.
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not $?) {
    throw "Não foi possível instalar as dependências."
}

# w Solicita cada token somente quando ele ainda não estiver definido nesta sessão.
if (-not $env:TMDB_API_KEY) {
    $secureToken = Read-Host "Informe o API Read Access Token do TMDb" -AsSecureString
    $tokenPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
    try {
        # w Remove espaços acidentais no começo ou no fim do token colado.
        $env:TMDB_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($tokenPointer).Trim()
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($tokenPointer)
    }
}

# w Impede iniciar a aplicação sem os tokens necessários.
if (-not $env:TMDB_API_KEY) {
    throw "TMDB_API_KEY é obrigatória."
}

# w Converte um banco antigo (chave imdb_id) para o schema com tmdb_id antes de iniciar a aplicação.
# w Bancos novos ou já migrados passam direto, sem pedir confirmação.
.\.venv\Scripts\python.exe migrate_cli.py
if (-not $?) {
    throw "A migração do banco não foi concluída. A aplicação não será iniciada."
}

# w Impede que o setup inicie uma segunda aplicação na mesma porta.
$portOwner = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue
if ($portOwner) {
    throw "A porta 5000 já está em uso pelo processo $($portOwner.OwningProcess). Feche esse processo e execute o setup novamente."
}

# w Mostra o IP da VPN (Tailscale), se instalada, para compartilhar com quem vai acessar remotamente.
$tailscaleIp = $null
try {
    $tailscaleIp = (tailscale ip -4 2>$null | Select-Object -First 1)
} catch {}
if ($tailscaleIp) {
    Write-Host "Acessível pela VPN em: http://$($tailscaleIp):5000" -ForegroundColor Cyan
} else {
    Write-Host "Tailscale não encontrado nesta máquina; acessível só localmente (http://127.0.0.1:5000) até a Etapa 7.1 ser configurada." -ForegroundColor Yellow
}

# w Inicia o Flask com os tokens disponíveis apenas nesta sessão.
.\.venv\Scripts\python.exe app.py
