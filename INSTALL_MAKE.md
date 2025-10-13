# Como Instalar e Usar o `make` no Windows

## ✅ `make` Instalado com Sucesso!

O GNU Make foi instalado via winget. Agora precisa completar a configuração:

---

## 🔧 Passos Finais (Necessários)

### **Opção 1: Reiniciar PowerShell (Mais Simples) ⭐**

1. **Feche** este terminal PowerShell
2. **Abra um NOVO** PowerShell
3. **Teste:**

```powershell
make --version
```

**Esperado:**
```
GNU Make 3.81
Copyright (C) 2006  Free Software Foundation, Inc.
This is free software; see the source for copying conditions.
...
```

Se funcionar, **pronto!** Pode usar:
```bash
make help
make test
make docker-build
```

---

### **Opção 2: Se Não Funcionar - Adicionar ao PATH Manualmente**

Se mesmo após reiniciar não funcionar, adicione ao PATH:

**1. Encontre onde foi instalado:**
```powershell
# Provavelmente está em:
C:\Program Files (x86)\GnuWin32\bin\
```

**2. Adicionar ao PATH:**

```powershell
# Abra PowerShell como Administrador e execute:
$makePath = "C:\Program Files (x86)\GnuWin32\bin"
[Environment]::SetEnvironmentVariable("Path", $env:Path + ";$makePath", "Machine")
```

**3. Reinicie PowerShell e teste:**
```powershell
make --version
```

---

### **Opção 3: Se o PATH Não Funcionar - Usar Caminho Completo**

Você pode usar o caminho completo temporariamente:

```powershell
& "C:\Program Files (x86)\GnuWin32\bin\make.exe" --version
& "C:\Program Files (x86)\GnuWin32\bin\make.exe" help
& "C:\Program Files (x86)\GnuWin32\bin\make.exe" test
```

---

## 🎯 Testar o Makefile

Depois de configurar, teste os comandos:

```bash
# Ver ajuda
make help

# Rodar testes
make test

# Ver versão do make
make --version

# Instalar dependências
make install
```

---

## 🔄 Alternativas ao GNU Make

Se tiver problemas com GnuWin32, há outras opções:

### **Opção A: Chocolatey**

```powershell
# Instalar Chocolatey (se não tiver)
Set-ExecutionPolicy Bypass -Scope Process -Force
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))

# Instalar make
choco install make
```

### **Opção B: Scoop**

```powershell
# Instalar Scoop (se não tiver)
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
irm get.scoop.sh | iex

# Instalar make
scoop install make
```

### **Opção C: Git Bash**

Se você tem o Git instalado, o Git Bash já vem com `make`:

1. Abra **Git Bash** (não PowerShell)
2. Navegue até o projeto
3. Use `make` normalmente

```bash
cd /c/Users/P02/energy-forecast-pt
make help
make test
```

### **Opção D: WSL (Windows Subsystem for Linux)**

```powershell
# Instalar WSL
wsl --install

# Dentro do WSL (Ubuntu)
sudo apt-get update
sudo apt-get install make
```

---

## 📊 Comparação das Opções

| Método | Facilidade | Recomendado |
|--------|-----------|-------------|
| **Reiniciar PowerShell** | ⭐⭐⭐⭐⭐ | ✅ Tente primeiro |
| **winget (já feito)** | ⭐⭐⭐⭐ | ✅ Instalado! |
| **Git Bash** | ⭐⭐⭐⭐ | ✅ Se tiver Git |
| **tasks.ps1** | ⭐⭐⭐⭐⭐ | ✅ Funciona sempre |
| **Chocolatey** | ⭐⭐⭐ | ⚠️ Se winget falhar |
| **WSL** | ⭐⭐ | ⚠️ Mais complexo |

---

## 🎯 Verificar Instalação

### **Comando 1: Verificar se make existe**

```powershell
where.exe make
```

**Esperado:** Deve mostrar o caminho, tipo:
```
C:\Program Files (x86)\GnuWin32\bin\make.exe
```

### **Comando 2: Verificar versão**

```powershell
make --version
```

**Esperado:**
```
GNU Make 3.81
...
```

### **Comando 3: Testar Makefile do projeto**

```powershell
cd C:\Users\P02\energy-forecast-pt
make help
```

**Esperado:** Deve mostrar a lista de comandos

---

## ⚠️ Problemas Comuns

### **Problema 1: "make: command not found"**

**Solução:**
1. Reinicie PowerShell
2. Ou use caminho completo: `& "C:\Program Files (x86)\GnuWin32\bin\make.exe"`

### **Problema 2: "Makefile:X: *** missing separator"**

**Solução:**
- O Makefile usa **tabs**, não espaços
- Nosso Makefile está correto, não mexa nele

### **Problema 3: "process_begin: CreateProcess(NULL, ...) failed"**

**Solução:**
- Alguns comandos do Makefile usam comandos Unix (`find`, `rm`)
- Use **Git Bash** em vez de PowerShell
- Ou use **tasks.ps1** que funciona nativamente no PowerShell

---

## 💡 Recomendação Final

### **Para Windows, você tem 2 opções excelentes:**

#### **Opção 1: Git Bash (com make) ⭐ RECOMENDADO**

```bash
# Abrir Git Bash (já vem com Git)
cd /c/Users/P02/energy-forecast-pt
make help
make test
```

**Vantagens:**
- ✅ `make` já funciona
- ✅ Comandos Unix funcionam
- ✅ Não precisa configurar nada

#### **Opção 2: PowerShell (com tasks.ps1) ⭐ RECOMENDADO**

```powershell
# PowerShell normal
cd C:\Users\P02\energy-forecast-pt
.\tasks.ps1 help
.\tasks.ps1 test
```

**Vantagens:**
- ✅ Feito especialmente para Windows
- ✅ Mesma funcionalidade que make
- ✅ Já funciona sem configurar

---

## 🎓 Resumo

| Você quer usar | Use isto | Como |
|----------------|----------|------|
| **Makefile** | Git Bash | Abra Git Bash → `make help` |
| **Nativo Windows** | tasks.ps1 | PowerShell → `.\tasks.ps1 help` |
| **Ambos** | Instale make + Git Bash | Siga passos acima |

---

## 🚀 Próximos Passos

1. **Reinicie seu PowerShell**
2. **Teste:** `make --version`
3. **Se funcionar:** Use `make help`, `make test`, etc.
4. **Se não funcionar:** Use Git Bash ou `tasks.ps1`

---

## 📞 Comandos de Teste

Depois de configurar, teste estes comandos:

```bash
# Ver ajuda do Makefile
make help

# Ver comandos disponíveis
make

# Rodar testes
make test

# Build Docker
make docker-build

# Limpar projeto
make clean
```

---

**Make instalado com sucesso! 🎉**

Agora reinicie o PowerShell e tente `make --version`
