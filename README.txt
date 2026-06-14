# Sistema SADI-AI
**Trabalho Final - DEC7129**

Sistema de Apoio ao Diagnóstico por Imagem com Inferência por MLLM.

**Alunos:** Kaio Martinhago e Pablo

## Visão geral

Este projeto consiste em uma aplicação desenvolvida com Django, integrada a um banco de dados MySQL, com suporte à recriação e população dinâmica da base de dados. Após a configuração inicial, o sistema permite acessar um painel administrativo e executar a carga automática dos dados necessários para o funcionamento da aplicação.

## Requisitos

Antes de iniciar, certifique-se de ter instalado em sua máquina:

- Python 3
- Git
- MySQL Server
- Um cliente de banco de dados MySQL, como o MySQL Workbench

## Configuração do modelo de IA (Ollama)

O sistema utiliza um modelo de visão computacional (MLLM) para analisar imagens médicas. O Ollama é o servidor local que executa esse modelo. Essa etapa deve ser feita antes de iniciar a aplicação.

### Instalação do Ollama

No Windows, execute o comando abaixo no PowerShell:

```powershell
irm https://ollama.com/install.ps1 | iex
```

### Inicialização do modelo

Após instalar o Ollama, abra um terminal separado e execute o comando abaixo para baixar e iniciar o modelo padrão do projeto:

```bash
ollama run moondream
```

O comando `ollama run` baixa o modelo automaticamente na primeira execução, caso ele ainda não esteja instalado, e já inicia o servidor local de IA. Mantenha esse terminal aberto enquanto utilizar o sistema, pois o Django se comunica com ele em segundo plano para gerar os laudos.

> **Atenção:** o Ollama deve estar em execução antes de subir o Django, pois a inferência é disparada automaticamente assim que imagens são enviadas ao sistema.

### Modelos disponíveis

O projeto usa por padrão a versão `moondream` (1.8B parâmetros), que é mais leve e indicada para testes. Modelos maiores podem gerar resultados melhores, mas exigem mais memória.

| Modelo | Tamanho | Recurso aproximado | Como iniciar |
|---|---|---|---|
| `moondream` (padrão) | 1.8B | ~1.7 GB de download | `ollama run moondream` |
| `llava` | 7B | ~5 GB de VRAM | `ollama run llava` |
| `llava:13b` | 13B | ~8 GB de VRAM | `ollama run llava:13b` |
| `llava:34b` | 34B | ~20 GB de VRAM | `ollama run llava:34b` |

Se quiser usar um modelo maior, além de executar o comando correspondente no Ollama, será necessário alterar o nome do modelo também no código da aplicação.

Abra o arquivo `conta/views.py`, localize a função `processar_ia_background` e altere o valor da chave `"model"` no dicionário `payload`:

```python
payload = {
    "model": "moondream",  # Altere aqui para o modelo desejado, como "llava" ou "llava:13b"
    ...
}
```

## Clonagem do repositório e ambiente virtual

Escolha uma pasta de sua preferência, abra outro terminal nesse local (um ficará executando o Ollama e o outro será usado para rodar o projeto) e clone o repositório:

```bash
git clone https://github.com/Kaio-Martinhago/Sistema-de-Apoio-ao-Diagnostico-por-Imagem-e-Inferencia-por-MLLM.git .
```

Em seguida, crie o ambiente virtual:

```powershell
python -m venv venv_tf_kaio_pablo
```

### Observação para Windows

Em alguns casos, o Windows Defender ou outro antivírus pode interromper a criação do ambiente virtual durante a etapa `ensurepip`, exibindo um erro semelhante a `KeyboardInterrupt`. Quando isso acontecer, execute o mesmo comando novamente. Normalmente, na segunda tentativa o ambiente é criado com sucesso.

Agora ative o ambiente virtual:

```powershell
.\venv_tf_kaio_pablo\Scripts\activate
```

Se tudo estiver correto, o nome do ambiente aparecerá no início da linha de comando.

Depois disso, instale as dependências do projeto:

```powershell
pip install -r requirements.txt
```

## Configuração do banco de dados MySQL

Antes de executar a aplicação, verifique se o servidor MySQL está em execução localmente.

No seu gerenciador SQL, crie um banco de dados vazio com o seguinte comando:

```sql
CREATE DATABASE projeto_final_kaio_pablo;
```

Depois, defina esse banco como o **schema padrão**.

Em seguida, dentro do projeto clonado, abra o arquivo:

```python
projeto_final/settings.py
```

Localize o dicionário `DATABASES` e substitua o valor do campo `PASSWORD` pela senha do usuário `root` do seu MySQL local:

```python
'PASSWORD': 'sua_senha',
```

## Migrações e criação do superusuário

Com o ambiente configurado e o banco pronto, execute os comandos abaixo no terminal para criar as tabelas nativas do Django e o usuário administrador:

```powershell
python manage.py migrate
python manage.py createsuperuser
```

Durante a criação do superusuário:

- O campo de e-mail pode ser deixado em branco.
- Ao digitar a senha, os caracteres não aparecerão no terminal. Isso é normal.
- Dependendo da senha escolhida, o Django pode informar que ela não atende aos requisitos mínimos.
- Para continuar mesmo assim, basta digitar `y` e pressionar Enter.

## Execução do sistema

Após concluir as etapas anteriores, inicie o servidor Django com o comando:

```powershell
python manage.py runserver
```

Depois, acesse a aplicação no navegador:

[http://127.0.0.1:8000/](http://127.0.0.1:8000/)

Faça login com o superusuário criado no passo anterior.

### Acesso à área administrativa do Django

Também é possível acessar a tela administrativa padrão do Django pelo endereço:

[http://127.0.0.1:8000/admin](http://127.0.0.1:8000/admin)

Nessa área, o usuário poderá editar, inserir ou excluir registros das tabelas disponíveis no sistema, de acordo com a lógica do banco de dados e com as restrições definidas pelas chaves primárias (PK) e chaves estrangeiras (FK).

## População dinâmica do banco

Após o login, o sistema redirecionará você para o painel de controle do banco de dados.

Nesse painel, clique no botão:

**Criar Tabelas e Popular**

Ao executar essa ação, o sistema irá:

- recriar a estrutura necessária do banco;
- executar os scripts DDL automaticamente;
- inserir os dados essenciais para o funcionamento da aplicação.

Isso inclui o cadastro de:

- Equipamentos
- Médicos
- Pacientes
- Exames
- Laudos gerados por Inteligência Artificial

## Fluxo resumido de execução

Para facilitar, o processo completo de execução do projeto é:

1. Iniciar o Ollama com `ollama run moondream`.
2. Clonar o repositório.
3. Criar e ativar o ambiente virtual.
4. Instalar as dependências.
5. Criar o banco de dados no MySQL.
6. Ajustar a senha do banco no arquivo `settings.py`.
7. Executar as migrações.
8. Criar o superusuário.
9. Iniciar o servidor Django.
10. Acessar o sistema no navegador.
11. Usar a opção de recriação e população do banco no painel.

## Observações finais

Este projeto foi desenvolvido para fins acadêmicos como trabalho final da disciplina DEC7129. Para evitar erros de configuração, recomenda-se seguir a ordem apresentada neste documento.