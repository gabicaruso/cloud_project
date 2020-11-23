# Para rodar o script usando o Pipenv
# pipenv run python3 script.py

# INSTALAÇÃO
# pip3 install boto3                | pip3 install boto3
# pip3 install -U python-dotenv     | pipenv install -U python-dotenv
# pip3 install awscli               | brew install awscli

# Para instalar mais pacotes:
# pipenv install <pacote>

# CONFIGURAÇÃO (apenas se não utilizar dotenv)
# aws configure

# IMPORTS
import boto3
from dotenv import load_dotenv
import os

# CONFIGURAÇÃO
# carregando dotenv
load_dotenv()

# definindo variáveis
AWS_ACCESS_KEY_ID = os.getenv("ACCESS_KEY")
AWS_SECRET_ACCESS_KEY = os.getenv("SECRET_KEY")
REGION_NAME = "us-east-2"       # Ohio
REGION_NAME_2 = "us-east-1"     # North Virginia

# IMPLEMENTAÇÃO
# sessão boto3
session1 = boto3.session.Session(aws_access_key_id=AWS_ACCESS_KEY_ID,
                                 aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                                 region_name=REGION_NAME)

session2 = boto3.session.Session(aws_access_key_id=AWS_ACCESS_KEY_ID,
                                 aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                                 region_name=REGION_NAME_2)

# clientes
ec2_oh = session1.resource("ec2")
ec2_nv = session2.resource("ec2")
client_oh = session1.client("ec2")
client_nv = session2.client("ec2")

# função para criar key pair

key_name = 'keyGabi'


def key_pair(client, key_name):
    client.delete_key_pair(KeyName=key_name)

    key_pair = client.create_key_pair(KeyName=key_name)
    key_name = "%s.pem" % key_name
    try:
        os.chmod(key_name, 0o777)
    except:
        pass

    with open(key_name, "w") as text_file:
        text_file.write(key_pair['KeyMaterial'])

    os.chmod(key_name, 0o400)

# Para acessar a maquina
# ssh -i ~/Documents/Insper/6semestre/cloud/projeto/keyGabi.pem ubuntu@3.134.94.134

# função para criar e autorizar grupos de segurança


db_group_name = 'DB_teste'
orm_group_name = 'ORM_teste'


def security_group(client, ec2, group_name):
    sg_response = client.describe_security_groups()
    for i in sg_response['SecurityGroups']:
        if i['GroupName'] == group_name:
            client.delete_security_group(GroupName=group_name)

    # describe vpc -> varia conforme regiao
    vpc_response = client.describe_vpcs()
    vpc_id = vpc_response['Vpcs'][0]['VpcId']

    ec2.create_security_group(
        Description='security group',
        GroupName=group_name,
        VpcId=vpc_id  # passar o describe pra ca e usar para o script inteiro
    )
    security_group = ec2.SecurityGroup('id')
    security_group.authorize_ingress(
        CidrIp='0.0.0.0/0',
        FromPort=22,
        GroupName=group_name,
        IpProtocol='TCP',
        ToPort=22,
    )
    security_group.authorize_ingress(
        CidrIp='0.0.0.0/0',
        FromPort=8080,
        GroupName=group_name,
        IpProtocol='TCP',
        ToPort=8080,
    )
    security_group.authorize_ingress(
        CidrIp='0.0.0.0/0',
        FromPort=5432,
        GroupName=group_name,
        IpProtocol='TCP',
        ToPort=5432,
    )

# função para criar instâncias


def create_instance(ec2):
    ec2.create_instances(
        ImageId="ami-0dd9f0e7df0f0a138",
        MinCount=1,
        MaxCount=1,
        InstanceType="t2.micro"
    )


# função para criar instâncias de banco de dados


def create_database_instance(ec2):
    # instance = ec2.Instance('id')
    # if instance['Tags'][0]['Value'] == 'DB_Gabi':
    #     instance.terminate()

    userdata = """#!/bin/sh
    sudo apt update
    sudo apt install postgresql postgresql-contrib -y
    sudo -u postgres psql -c "CREATE USER cloud WITH PASSWORD 'cloud';"
    sudo -u postgres createdb -O cloud tasks
    sed -i "s/#listen_addresses = 'localhost'/listen_addresses = '*'/g" /etc/postgresql/10/main/postgresql.conf
    echo host all all 192.168.0.0/20 trust >> /etc/postgresql/10/main/pg_hba.conf
    exit
    sudo ufw allow 5432/tcp
    sudo systemctl restart postgresql
    """
    ec2.create_instances(
        ImageId="ami-0dd9f0e7df0f0a138",  # AMI Ubunto 18.04 para Ohio
        MinCount=1,
        MaxCount=1,
        InstanceType="t2.micro",
        KeyName=key_name,  # key_pair
        SecurityGroups=[db_group_name],
        UserData=userdata,
        TagSpecifications=[
            {
                'ResourceType': 'instance',
                'Tags': [
                    {
                        'Key': 'Name',
                        'Value': 'DB_Gabi'
                    },
                ]
            },
        ]
    )

# Para testar o postgres
# psql -U cloud -d tasks -h localhost

# função para criar instâncias de banco de dados


def create_orm_instance(ec2):
    # instance = ec2.Instance('id')
    # if instance['Tags'][0]['Value'] == 'ORM_Gabi':
    #     instance.terminate()

    userdata = """#!/bin/sh
    git clone https://github.com/gabicaruso/tasks.git
    ./tasks/install.sh
    """
    ec2.create_instances(
        ImageId="ami-00ddb0e5626798373",  # AMI Ubunto 18.04 para North Virginia
        MinCount=1,
        MaxCount=1,
        InstanceType="t2.micro",
        KeyName=key_name,  # key_pair
        SecurityGroups=[orm_group_name],
        UserData=userdata,
        TagSpecifications=[
            {
                'ResourceType': 'instance',
                'Tags': [
                    {
                        'Key': 'Name',
                        'Value': 'ORM_Gabi'
                    },
                ]
            },
        ]
    )


# Rodando funções
key_pair(client_oh, key_name)
security_group(client_oh, ec2_oh, db_group_name)
key_pair(client_nv, key_name)
security_group(client_nv, ec2_nv, orm_group_name)
# create_instance(ec2)
create_database_instance(ec2_oh)
create_orm_instance(ec2_nv)
