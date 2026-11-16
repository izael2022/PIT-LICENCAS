# PIT LICENCAS

Servidor central de licencas do PIT ADICIONADOR.

## Estado atual

Esta e a primeira versao da API. Ela oferece:
- verificacao de saude em `/health`;
- criacao administrativa de licencas em `POST /admin/licenses`;
- ativacao de uma licenca em um dispositivo em `POST /activate`;
- validacao de sessao em `POST /validate`;
- bloqueio e listagem administrativa.

## Configuracao obrigatoria na Discloud

Configure a variavel de ambiente `ADMIN_TOKEN` com um segredo forte e exclusivo. Nao coloque esse segredo no GitHub nem no aplicativo desktop.

Opcionalmente, configure `DATABASE_PATH` para um caminho de armazenamento persistente fornecido pela hospedagem. O caminho padrao e `data/licencas.db`.

## Importante antes de vender

- O repositorio contem somente codigo; nao coloque chaves, senhas, tokens ou dados de clientes nele.
- Confirme que o armazenamento usado pelo banco SQLite persiste entre reinicializacoes e novos deploys.
- A API ainda precisa ser integrada ao cliente PIT ADICIONADOR e testada antes de ser usada comercialmente.
- Use HTTPS no dominio publicado.
