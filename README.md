# Projeto Cloud

*Projeto Final da disciplina de Computação em Nuvem - 2020.2*

## Descrição

Um sistema ORM multi-cloud com Load Balancer e Autoscalling implementado em Python e Boto3.

  - [X] Possui um aplicação cliente;
  - [X] Possui um script de implantação automático (sem intervenção manual).
  
## Requisitos

  - [X] Cria uma instância em Ohio que instala o Banco de Dados (Postgres);
  - [X] Cria um Security Group (liberando todas as portas necessárias);
  - [X] Cria outra instância em North Virginia que instala o ORM para apontando para o Banco de Dados;
  - [X] Cria um Load Balancer e um Auto Scaling Group para instalar o ORM (ao invês da instância criada anteriormente);
  - [X] Faxz um client para consumir os endpoints do terminal;
  - [X] Destroi os itens criados anteriormente toda a vez que roda o script.
  
## Execução

### Instalação
```python
pip3 install boto3
pip3 install -U python-dotenv
pip3 install awscli
pip3 install requests
```

___

### Para rodar o script:
```python
python3 script.py
```

___

### Client

#### Para pegar todas as tasks:
```python
python3 client.py get_tasks
```

#### Para adicionar uma task:
```python
python3 client.py add_task <title> <description>
```

#### Para deletar todas as tasks:
```python
python3 client.py del_tasks
```

#### Para acessar o site:
```
http://<LoadBalancerDNS>/tasks/
http://gabiormlb-xxxxxxxxx.us-east-1.elb.amazonaws.com/tasks/
```

___

### Alternativa: Instalação do Pipenv
```python
pip3 install pipenv
```

### Para instalar pacotes com o Pipenv:
```python
pipenv install <pacote>
```

### Para rodar arquivos Python usando o Pipenv:
```python
pipenv run python3 <file>
```

___

### Configuração *(apenas se não utilizar dotenv)*
```
aws configure
```
