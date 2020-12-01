# Para rodar o script usando o Pipenv
# pipenv run python3 script.py

# =====================================================================================
# IMPORTS
# =====================================================================================
import boto3
import os
import pprint
import time
pp = pprint.PrettyPrinter(indent=4)

# =====================================================================================
# GLOBAL CONSTANTS
# =====================================================================================
AWS_ACCESS_KEY_ID = os.getenv("ACCESS_KEY")
AWS_SECRET_ACCESS_KEY = os.getenv("SECRET_KEY")
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
client_lbv2 = SESSION_NV.client("elbv2")
client_as = SESSION_NV.client("autoscaling")
client_cw = SESSION_NV.client("cloudwatch")

# Get VPC ids for both regions
VPC_OH = client_oh.describe_vpcs()["Vpcs"][0]["VpcId"]
VPC_NV = client_nv.describe_vpcs()["Vpcs"][0]["VpcId"]

# =====================================================================================
# FUNCTIONS
# =====================================================================================


def key_pair(client, name):
    print(f"[LOG] Deleting KeyPair '{name}'...")
    client.delete_key_pair(KeyName=name)
    print("[LOG] Deleted.")

    print(f"[LOG] Creating KeyPair '{name}'...")
    key_pair = client.create_key_pair(KeyName=name)
    name = "%s.pem" % name
    try:
        os.chmod(name, 0o777)
    except:
        pass

    with open(name, "w") as text_file:
        text_file.write(key_pair["KeyMaterial"])

    os.chmod(name, 0o400)
    print("[LOG] Created.")


def create_security_group(client, ec2, vpc_id, name):
    print(f"[LOG] Creating SecurityGroup '{name}'...")
    try:
        response = ec2.create_security_group(
            Description="SecurityGroup",
            GroupName=name,
            VpcId=vpc_id,  # passar o describe pra ca e usar para o script inteiro
        )
        print("[LOG] Created.")
    except Exception as e:
        print(f"[LOG] Could not create SecurityGroup '{name}'. ERROR: {e}.")
        return

    print("[LOG] Creating SecurityGroup rules...")
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

    client.authorize_security_group_ingress(
        GroupName=name,
        IpPermissions=[
            {
                "FromPort": 80,
                "ToPort": 80,
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

    print("[LOG] Created.")
    return response.group_id


def delete_security_group(client, name):
    print(f"[LOG] Deleting SecurityGroup '{name}'")
    try:
        client.delete_security_group(GroupName=name)
        print("[LOG] Deleted.")
    except Exception as e:
        print(f"[LOG] Could not delete SecurityGroup '{name}'. ERROR: {e}.")


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
        f"[LOG] Terminating instances with name '{name}'. IDs: {instance_ids}.")
    client.terminate_instances(
        InstanceIds=instance_ids,
    )

    print("[LOG] Waiting...")
    waiter = client.get_waiter("instance_terminated")
    waiter.wait(InstanceIds=instance_ids)
    print("[LOG] Done.")


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

    print(f"[LOG] Creating Database instance with name '{name}'...")
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
    print(f"[LOG] Database instance ID: {instance.instance_id}.")

    waiter = client.get_waiter("instance_running")
    waiter.wait(InstanceIds=[instance.instance_id])
    print("[LOG] Database instance is now running.")

    response = client.describe_instances(
        InstanceIds=[
            instance.instance_id,
        ],
    )

    if len(response["Reservations"]) > 0:
        instance_ip = response["Reservations"][0]["Instances"][0]["PublicIpAddress"]
        print(f"[LOG] Database instance public IP: {instance_ip}")
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

    print(f"[LOG] Creating ORM instance with name '{name}'...")
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
    print(f"[LOG] ORM instance ID: {instance.instance_id}.")

    waiter = client.get_waiter("instance_running")
    waiter.wait(InstanceIds=[instance.instance_id])
    print(f"[LOG] ORM instance is now running.")

    response = client.describe_instances(
        InstanceIds=[
            instance.instance_id,
        ],
    )

    if len(response["Reservations"]) > 0:
        instance_id = response["Reservations"][0]["Instances"][0]["InstanceId"]
        print(f"[LOG] DB instance public ID: {instance_id}.")
        return instance_id
    else:
        print("[LOG] Error getting DB IP address.")


def delete_load_balancer(client_lb, client_lbv2, name):
    print(f"[LOG] Deleting LoadBalancer '{name}'...")
    try:
        client_lb.delete_load_balancer(
            LoadBalancerName=name
        )

        waiter = client_lbv2.get_waiter('load_balancers_deleted')
        waiter.wait(Names=[name])

        print("[LOG] Deleted.")
    except Exception as e:
        print(f"[LOG] LoadBalancer '{name}' not found. ERROR: {e}.")


def create_load_balancer(client, client_lb, name, sg_name):
    print(f"[LOG] Creating LoadBalancer with name '{name}'...")

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
                'InstancePort': 8080,
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
    print("[LOG] Created.")

    print("[LOG] Adding health check...")
    response = client_lb.configure_health_check(
        LoadBalancerName=name,
        HealthCheck={
            'Target': 'TCP:8080',
            'Interval': 30,
            'Timeout': 15,
            'UnhealthyThreshold': 5,
            'HealthyThreshold': 2
        }
    )
    print("[LOG] Done.")


def delete_auto_scaling_group(client_as, name):
    print(f"[LOG] Deleting AutoScalingGroup '{name}'...")
    try:
        client_as.delete_auto_scaling_group(
            AutoScalingGroupName=name,
            ForceDelete=True
        )
        response = client_as.describe_auto_scaling_groups(
            AutoScalingGroupNames=[
                name,
            ]
        )

        while len(response["AutoScalingGroups"]) > 0:
            print(
                f"[LOG] Waiting for AutoScalingGroup '{name}' to be deleted.")
            time.sleep(8)
            response = client_as.describe_auto_scaling_groups(
                AutoScalingGroupNames=[
                    name,
                ],
            )

        print("[LOG] Deleted.")
    except Exception as e:
        print(f"[LOG] AutoScalingGroup '{name}' not found. ERROR: {e}.")


def create_auto_scaling_group(client, client_as, name, lc_name, lb_name):
    print(f"[LOG] Creating AutoScalingGroup with name '{name}'...")

    client_as.create_auto_scaling_group(
        AutoScalingGroupName=name,
        HealthCheckGracePeriod=120,
        HealthCheckType='ELB',
        LaunchConfigurationName=lc_name,
        LoadBalancerNames=[
            lb_name,
        ],
        MaxSize=3,
        MinSize=1,
        Tags=[
            {
                'Key': 'Name',
                'Value': 'GABI_ASG'
            },
        ],
        AvailabilityZones=["us-east-1a", "us-east-1b"]
    )
    print("[LOG] Created.")


def delete_launch_configuration(client_as, name):
    print(f"[LOG] Deleting LaunchConfiguration '{name}'...")
    try:
        client_as.delete_launch_configuration(
            LaunchConfigurationName=name
        )
        print("[LOG] Deleted.")
    except Exception as e:
        print(f"[LOG] LaunchConfiguration '{name}' not found. ERROR: {e}.")


def create_launch_configuration(client_as, name, sg_id, key_name, db_pip):
    print(f"[LOG] Creating LaunchConfiguration with name '{name}'...")

    userdata = f"""#!/bin/sh
    cd /home/ubuntu
    sudo apt update
    git clone https://github.com/gabicaruso/tasks.git
    cd tasks
    sudo sed -i 's/XXXX/{db_pip}/g' /home/ubuntu/tasks/portfolio/settings.py
    ./install.sh
    sudo reboot
    """

    try:
        client_as.create_launch_configuration(
            LaunchConfigurationName=name,
            ImageId="ami-00ddb0e5626798373",  # AMI Ubunto 18.04 para North Virginia
            KeyName=key_name,
            SecurityGroups=[
                sg_id,
            ],
            UserData=userdata,
            InstanceType='t2.micro',
            AssociatePublicIpAddress=True,
        )
        print("[LOG] Created.")
    except Exception as e:
        print(
            f"[LOG] Could not create LaunchConfiguration '{name}'. ERROR: {e}.")


def put_extend_scaling_policy(client_as, client_cw, name, alarm_name, as_name):
    print(f"[LOG] Creating ScalingPolicy with name '{name}'...")
    response = client_as.put_scaling_policy(
        AutoScalingGroupName=as_name,
        PolicyName=name,
        PolicyType='SimpleScaling',
        AdjustmentType='ChangeInCapacity',
        ScalingAdjustment=1,
        Cooldown=120,
    )
    policyARN = response['PolicyARN']
    client_cw.put_metric_alarm(
        AlarmName=alarm_name,
        AlarmDescription="Metade da CPU",
        ActionsEnabled=True,
        AlarmActions=[
            policyARN,
        ],
        MetricName='CPUUtilization',
        Namespace='AWS/EC2',
        Statistic='Average',
        Dimensions=[
            {
                'Name': 'AutoScalingGroupName',
                'Value': as_name
            },
        ],
        Period=120,
        Unit='Percent',
        EvaluationPeriods=2,
        DatapointsToAlarm=2,
        Threshold=50.0,
        ComparisonOperator='GreaterThanOrEqualToThreshold',
        TreatMissingData='ignore',
    )
    print("[LOG] Created.")


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
    orm_lc_name = "GABI_ORM_LC"
    sp_name = "GABI_SP"
    cw_name = "GABI_CW"

    # Create key pair
    key_pair(client_oh, kp_name_oh)
    key_pair(client_nv, kp_name_nv)

    # Delete instances
    delete_instance(client_oh, ec2_oh, db_i_name)

    # Delete LB
    delete_load_balancer(client_lb, client_lbv2, orm_lb_name)

    # Delete AS
    delete_auto_scaling_group(client_as, orm_as_name)

    # Delete LC
    delete_launch_configuration(client_as, orm_lc_name)

    # Delete SGs
    delete_security_group(client_oh, db_sg_name)
    delete_security_group(client_nv, orm_sg_name)

    # Create SGs
    create_security_group(client_oh, ec2_oh, VPC_OH, db_sg_name)
    orm_sg_id = create_security_group(client_nv, ec2_nv, VPC_NV, orm_sg_name)

    # Create instances
    db_pip = create_database_instance(
        client_oh, ec2_oh, db_i_name, db_sg_name, kp_name_oh)

    # Create LC
    create_launch_configuration(
        client_as, orm_lc_name, orm_sg_id, kp_name_nv, db_pip)

    # Create LB
    create_load_balancer(client_nv, client_lb, orm_lb_name, orm_sg_name)

    # Create AS
    create_auto_scaling_group(client_nv, client_as,
                              orm_as_name, orm_lc_name, orm_lb_name)

    # Put SP
    put_extend_scaling_policy(client_as, client_cw,
                              sp_name, cw_name, orm_as_name)

    print("[LOG] Wait for the first instance GABI_ASG to be initialized on AWS EC2.")
