# Para rodar o script usando o Pipenv
# pipenv run python3 script.py

# =====================================================================================
# IMPORTS
# =====================================================================================
import boto3
import os
import pprint
pp = pprint.PrettyPrinter(indent=4)

# =====================================================================================
# GLOBAL CONSTANTS
# =====================================================================================
AWS_ACCESS_KEY_ID = "AKIAQV7Q65JNZLLCI5TS"
AWS_SECRET_ACCESS_KEY = "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"
REGION_NAME = "us-east-2"  # Ohio
REGION_NAME_2 = "us-east-1"  # North Virginia

# IMPLEMENTAÇÃO
# sessão boto3
SESSION_OH = boto3.session.Session(
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=REGION_NAME,
)

SESSION_NV = boto3.session.Session(
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=REGION_NAME_2,
)

# Create clients
ec2_oh = SESSION_OH.resource("ec2")
ec2_nv = SESSION_NV.resource("ec2")
client_oh = SESSION_OH.client("ec2")
client_nv = SESSION_NV.client("ec2")
client_lb = SESSION_NV.client("elb")
client_as = SESSION_NV.client("autoscaling")

# Get VPC ids for both regions
VPC_OH = client_oh.describe_vpcs()["Vpcs"][0]["VpcId"]
VPC_NV = client_nv.describe_vpcs()["Vpcs"][0]["VpcId"]

# =====================================================================================
# FUNCTIONS
# =====================================================================================

# função para criar key pair

# key_name = 'keyGabi'


def key_pair(client, key_name):
    client.delete_key_pair(KeyName=key_name)

    key_pair = client.create_key_pair(KeyName=key_name)
    key_name = "%s.pem" % key_name
    try:
        os.chmod(key_name, 0o777)
    except:
        pass

    with open(key_name, "w") as text_file:
        text_file.write(key_pair["KeyMaterial"])

    os.chmod(key_name, 0o400)


def create_security_group(client, ec2, vpc_id, name):
    print(f"[LOG] Creating SG '{name}'...")
    try:
        ec2.create_security_group(
            Description="security group",
            GroupName=name,
            VpcId=vpc_id,  # passar o describe pra ca e usar para o script inteiro
        )
        print(f"[LOG] Created.")
    except Exception as e:
        print(f"[LOG] Could not create SG '{name}'. Error: {e}")
        return

    print(f"[LOG] Creating SG rules...")
    client.authorize_security_group_ingress(
        GroupName=name,
        IpPermissions=[
            {
                "FromPort": 22,
                "ToPort": 22,
                "IpProtocol": "tcp",
                "IpRanges": [
                    {
                        "CidrIp": "0.0.0.0/0",
                        "Description": "SSH",
                    },
                ],
            },
        ],
    )

    client.authorize_security_group_ingress(
        GroupName=name,
        IpPermissions=[
            {
                "FromPort": 5432,
                "ToPort": 5432,
                "IpProtocol": "tcp",
                "IpRanges": [
                    {
                        "CidrIp": "0.0.0.0/0",
                        "Description": "POSTGRES",
                    },
                ],
            },
        ],
    )

    client.authorize_security_group_ingress(
        GroupName=name,
        IpPermissions=[
            {
                "FromPort": 8080,
                "ToPort": 8080,
                "IpProtocol": "tcp",
                "IpRanges": [
                    {
                        "CidrIp": "0.0.0.0/0",
                        "Description": "HTTP",
                    },
                ],
            },
        ],
    )

    print(f"[LOG] Created.")


def delete_security_group(client, name):
    print(f"[LOG] Deleting SG '{name}'")
    try:
        client.delete_security_group(GroupName=name)
        print(f"[LOG] Deleted")
    except Exception as e:
        print(f"[LOG] Could not delete. Error: {e}")


def delete_instance(client, ec2, name):
    instance_ids = get_instance_id(client, name)
    if instance_ids == None or len(instance_ids) == 0:
        print(f"[LOG] Could not delete instance '{name}'.")
        return
    if len(instance_ids) > 1:
        print(
            f"[LOG] Multiple instance with name '{name}' found. Deleting all of them..."
        )

    print(
        f"[LOG] Terminating instances with name '{name}'. IDs: {instance_ids}")
    client.terminate_instances(
        InstanceIds=instance_ids,
    )

    print(f"[LOG] Waiting...")
    waiter = client.get_waiter("instance_terminated")
    waiter.wait(InstanceIds=instance_ids)
    print(f"[LOG] Done.")


def get_instance_id(client, name):
    instances = client.describe_instances(
        Filters=[
            {
                "Name": "tag:Name",
                "Values": [
                    name,
                ],
            },
            {
                "Name": "instance-state-name",
                "Values": [
                    "pending",
                    "running",
                    "shutting-down",
                    "stopping",
                    "stopped",
                ],
            },
        ]
    )

    ids = []
    if len(instances["Reservations"]) > 0:
        for reservation in instances["Reservations"]:
            for instance in reservation["Instances"]:
                ids.append(instance["InstanceId"])
        return ids
    else:
        print(f"[LOG] No instance '{name}' found.")
        return None


def create_database_instance(client, ec2, name, db_sg_name, key_name):
    userdata = """#!/bin/sh
    sudo apt update
    sudo apt install postgresql postgresql-contrib -y
    sudo -u postgres psql -c "CREATE USER cloud WITH PASSWORD 'cloud';"
    sudo -u postgres createdb -O cloud tasks
    sed -i "s/#listen_addresses = 'localhost'/listen_addresses = '*'/g" /etc/postgresql/10/main/postgresql.conf
    echo host all all 0.0.0.0/0 trust >> /etc/postgresql/10/main/pg_hba.conf
    sudo ufw allow 5432/tcp
    sudo systemctl restart postgresql
    """

    print(f"[LOG] Creating DB instance...")
    instances = ec2.create_instances(
        ImageId="ami-0dd9f0e7df0f0a138",  # AMI Ubunto 18.04 para Ohio
        MinCount=1,
        MaxCount=1,
        InstanceType="t2.micro",
        KeyName=key_name,  # key_pair
        SecurityGroups=[db_sg_name],
        UserData=userdata,
        TagSpecifications=[
            {
                "ResourceType": "instance",
                "Tags": [
                    {"Key": "Name", "Value": name},
                ],
            },
        ],
    )

    instance = instances[0]
    print(f"[LOG] DB instance ID: {instance.instance_id}")

    waiter = client.get_waiter("instance_running")
    waiter.wait(InstanceIds=[instance.instance_id])
    print(f"[LOG] DB instance is running now.")

    response = client.describe_instances(
        InstanceIds=[
            instance.instance_id,
        ],
    )

    if len(response["Reservations"]) > 0:
        instance_ip = response["Reservations"][0]["Instances"][0]["PublicIpAddress"]
        print(f"[LOG] DB instance public IP: {instance_ip}")
        return instance_ip
    else:
        print("[LOG] Error getting DB IP address.")


def create_orm_instance(client, ec2, name, orm_sg_name, key_name, db_pip):
    userdata = f"""#!/bin/sh
    cd /home/ubuntu
    sudo apt update
    git clone https://github.com/gabicaruso/tasks.git
    cd tasks
    sudo sed -i 's/XXXX/{db_pip}/g' /home/ubuntu/tasks/portfolio/settings.py
    ./install.sh
    sudo reboot
    """

    print(f"[LOG] Creating ORM instance...")
    instances = ec2.create_instances(
        ImageId="ami-00ddb0e5626798373",  # AMI Ubunto 18.04 para North Virginia
        MinCount=1,
        MaxCount=1,
        InstanceType="t2.micro",
        KeyName=key_name,  # key_pair
        SecurityGroups=[orm_sg_name],
        UserData=userdata,
        TagSpecifications=[
            {
                "ResourceType": "instance",
                "Tags": [
                    {"Key": "Name", "Value": name},
                ],
            },
        ],
    )

    instance = instances[0]
    print(f"[LOG] ORM instance ID: {instance.instance_id}")

    waiter = client.get_waiter("instance_running")
    waiter.wait(InstanceIds=[instance.instance_id])
    print(f"[LOG] ORM instance is running now.")

    response = client.describe_instances(
        InstanceIds=[
            instance.instance_id,
        ],
    )

    if len(response["Reservations"]) > 0:
        instance_id = response["Reservations"][0]["Instances"][0]["InstanceId"]
        print(f"[LOG] DB instance public ID: {instance_id}")
        return instance_id
    else:
        print("[LOG] Error getting DB IP address.")


def create_ami(client, name, orm_id):
    print(f"[LOG] Creating ORM image...")
    client.create_image(
        InstanceId=orm_id,
        Name=name
    )
    print(f"[LOG] Created.")


# def deregister_ami(client, name, orm_id):
#     pp = pprint.PrettyPrinter(indent=4)
#     response = client.describe_images(
#         Filters=[
#             {
#                 'Name': 'tag:Name',
#                 'Values': [
#                     name,
#                 ],
#             },
#         ],
#     )
#     pp.pprint(response["Images"])

    # response = client.deregister_image(
    #     ImageId='string',
    # )

    # if len(response["Images"]) > 0:
    #     print("[LOG] ORM image already created.")
    # else:
    #     print(f"[LOG] Creating ORM image...")
    #     client.create_image(
    #         InstanceId=orm_id,
    #         Name=name
    #     )
    #     print(f"[LOG] Created.")

def delete_load_balancer(client_lb, name):
    print(f"[LOG] Deleting LB...")

    response = client_lb.describe_load_balancers()
    for i in response['LoadBalancerDescriptions']:
        if i['LoadBalancerName'] == name:
            client_lb.delete_load_balancer(
                LoadBalancerName=name
            )
            print("[LOG] LB deleted.")
        else:
            print("[LOG] LB not found.")


def create_load_balancer(client, client_lb, name, sg_name):
    print(f"[LOG] Creating Load Balancer...")

    sg_id = client.describe_security_groups(
        GroupNames=[sg_name]
    )["SecurityGroups"][0]["GroupId"]

    response = client.describe_subnets()
    subnets = []
    for subnet in response['Subnets']:
        subnets.append(subnet['SubnetId'])

    client_lb.create_load_balancer(
        LoadBalancerName=name,
        Listeners=[
            {
                'InstancePort': 80,
                'InstanceProtocol': 'HTTP',
                'LoadBalancerPort': 80,
                'Protocol': 'HTTP',
            },
        ],
        Subnets=subnets,
        SecurityGroups=[
            sg_id,
        ],
        Tags=[
            {
                'Key': 'Name',
                'Value': 'LBGabi'
            },
        ]
    )
    # waiter = client.get_waiter("load_balancer_exists")
    # waiter.wait(InstanceIds=[instance.instance_id])
    # print(f"[LOG] LB is running now.")
    print(f"[LOG] Created.")


def create_auto_scaling_group(client_as, name, lb_name, orm_id):
    print(f"[LOG] Creating Auto Scaling Group...")
    client_as.create_auto_scaling_group(
        AutoScalingGroupName=name,
        HealthCheckGracePeriod=120,
        HealthCheckType='ELB',
        InstanceId=orm_id,
        LoadBalancerNames=[
            lb_name,
        ],
        MaxSize=3,
        MinSize=1,
        Tags=[
            {
                'Key': 'Name',
                'Value': 'ASGabi'
            },
        ]
    )
    print(f"[LOG] Created.")


if __name__ == "__main__":
    kp_name_oh = "GABI_KEY_OH"
    kp_name_nv = "GABI_KEY_NV"
    db_i_name = "GABI_DB"
    db_sg_name = "GABI_DB_SG"
    orm_i_name = "GABI_ORM"
    orm_sg_name = "GABI_ORM_SG"
    orm_ami_name = "GABI_ORM_AMI"
    orm_lb_name = "GabiOrmLB"
    orm_as_name = "GABI_ORM_AS"

    # Create key pair
    key_pair(client_oh, kp_name_oh)
    key_pair(client_nv, kp_name_nv)

    # Delete instances
    delete_instance(client_oh, ec2_oh, db_i_name)
    delete_instance(client_nv, ec2_nv, orm_i_name)

    # Delete SGs
    delete_security_group(client_oh, db_sg_name)
    delete_security_group(client_nv, orm_sg_name)

    # Delete LB
    delete_load_balancer(client_lb, orm_lb_name)

    # Create SGs
    create_security_group(client_oh, ec2_oh, VPC_OH, db_sg_name)
    create_security_group(client_nv, ec2_nv, VPC_NV, orm_sg_name)

    # Create instances
    db_pip = create_database_instance(
        client_oh, ec2_oh, db_i_name, db_sg_name, kp_name_oh)
    orm_id = create_orm_instance(
        client_nv, ec2_nv, orm_i_name, orm_sg_name, kp_name_nv, db_pip)

    # Create image
    # deregister_ami(client_nv, orm_ami_name, 'i-00ec7c9c6fca07916')
    # create_ami(client_nv, orm_ami_name, 'i-00ec7c9c6fca07916')

    # Create LB
    create_load_balancer(client_nv, client_lb, orm_lb_name, orm_sg_name)

    # Create AS
    create_auto_scaling_group(client_as, orm_as_name, orm_lb_name, orm_id)
