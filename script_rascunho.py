# Para rodar o script usando o Pipenv
# pipenv run python3 script_rascunho.py

# INSTALAÇÃO
# pip3 install boto3                | pipenv install boto3
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
import pprint
pp = pprint.PrettyPrinter(indent=4)

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
client_lb = session2.client('elb')

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


def create_security_group(client, ec2, group_name):
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


def delete_security_group(client, ec2, group_name):
    sg_response = client.describe_security_groups()
    for i in sg_response['SecurityGroups']:
        if i['GroupName'] == group_name:
            client.delete_security_group(GroupName=group_name)


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

# função para criar instâncias orm


def create_orm_instance(ec2):
    # instance = ec2.Instance('id')
    # if instance['Tags'][0]['Value'] == 'ORM_Gabi':
    #     instance.terminate()
    db_ip = get_instance_ip(client_oh, 'DB_Gabi')

    userdata = """#!/bin/sh
    cd /home/ubuntu
    sudo apt update
    git clone https://github.com/gabicaruso/tasks.git
    cd tasks
    sudo sed -i 's/XXXX/{}/g' /home/ubuntu/tasks/portfolio/settings.py
    .install.sh
    sudo reboot
    """.format(db_ip)

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


# função para deletar instâncias


def delete_instance(ec2, client, instance_name):
    instance_id = get_instance_id(client, instance_name)
    print(instance_id)

    instance = ec2.Instance(instance_id)
    instance.terminate()

    waiter = client.get_waiter('instance_terminated')
    waiter.wait(InstanceIds=[instance_id])


# função para encontrar instâncias


def get_instance_id(client, instance_name):
    found = False
    while not found:
        response = client.describe_instances(Filters=[
            {
                'Name': 'tag:Name',
                'Values': [
                    key_name,
                ]
            },
        ])

        for each in response['Reservations']:
            if each['Instances'][0]['State']['Name'] == 'running':
                print('if')
                found = True
                instance_id = each['Instances'][0]['InstanceId']
        print(found)

    return instance_id


# função para encontrar instâncias


def get_instance_ip(client, instance_name):
    instances = client.describe_instances(
        Filters=[
            {
                'Name': 'tag:Name',
                'Values': [
                    instance_name
                ]
            },
            {
                'Name': 'instance-state-name',
                'Values': [
                    'running'
                ]
            }
        ],
    )["Reservations"]
    # pp.pprint(instances)

    instance_ip = instances[0]['Instances'][0]['PublicIpAddress']
    pp.pprint(instance_ip)
    return instance_ip


# função para verificar o status das instâncias


def get_instance_status(client, instance_name):
    instances = client.describe_instances(
        Filters=[
            {
                'Name': 'tag:Name',
                'Values': [
                    instance_name,
                ]
            }
        ],
    )["Reservations"]

    instance_status = instances[0]['Instances'][0]['State']['Name']
    return instance_status


# função para criar uma imagem


def ami(client, instance_name, ami_name):
    instance_id = get_instance_id(client, instance_name)
    client.create_image(
        InstanceId=instance_id,
        Name=ami_name,
    )


# função para criar load balancer


def load_balancer(client, client_lb, group_name):
    lbs = client_lb.describe_load_balancers()

    lb = client.create_load_balancer(
        LoadBalancerName='LB_Gabi',
        Listeners=[
            {
                'Protocol': 'string',
                'LoadBalancerPort': 123,
                'InstanceProtocol': 'string',
                'InstancePort': 123,
                'SSLCertificateId': 'string'
            },
        ],
        AvailabilityZones=[
            'string',
        ],
        Subnets=[
            'string',
        ],
        SecurityGroups=[
            'string',
        ],
        Scheme='string',
        Tags=[
            {
                'Key': 'string',
                'Value': 'string'
            },
        ]
    )


# Rodando funções
# delete_instance(ec2_oh, client_oh, 'DB_Gabi')
# delete_instance(ec2_nv, client_nv, 'ORM_Gabi')

key_pair(client_oh, key_name)
security_group(client_oh, ec2_oh, db_group_name)
key_pair(client_nv, key_name)
security_group(client_nv, ec2_nv, orm_group_name)
# create_instance(ec2)
create_database_instance(ec2_oh)
create_orm_instance(ec2_nv)
# ami(client_nv, 'ORM_Gabi', 'ORM_image')
# get_instance_ip(client_oh, 'DB_Gabi')
# get_instance_status(client_oh, 'DB_Gabi')
