# FreeIPA Dev Environment Implementation

## Overview

This document describes the minimal FreeIPA setup for the Astra dev environment on AWS, based on `fedora-infra/tiny-stage`.

## What Was Implemented

### 1. Terraform Module (`infra/modules/freeipa/`)

**Purpose:** Provision a single Fedora EC2 instance for FreeIPA with proper security groups.

**Key Features:**
- Uses latest Fedora Cloud AMI (Fedora 43)
- Instance type: `t3.medium` (FreeIPA needs reasonable resources)
- 30 GB encrypted EBS volume
- Security groups for all IPA ports (HTTP/S, LDAP/S, Kerberos, DNS)
- Optional Elastic IP for stable external access
- Generates Ansible inventory automatically

**Security Model:**
- ALB/web UI access: configurable CIDRs (default: `0.0.0.0/0` for dev)
- LDAP/Kerberos: restricted to VPC CIDR (ECS tasks)
- SSH: configurable CIDRs for admin access

### 2. Ansible Playbook (`ansible/freeipa_setup.yml`)

**Purpose:** Fully automated IPA installation with FAS extensions.

**Installation Steps:**
1. Updates system packages
2. Installs `freeipa-server`, `freeipa-server-dns`, `python3-ipalib`
3. Runs `ipa-server-install` with DNS setup, no NTP, unattended mode
4. Clones and installs `freeipa-fas` extensions from `github.com/fedora-infra/freeipa-fas`
5. Restarts IPA to load FAS plugins
6. Verifies FAS commands are available (`ipa fasagreement-help`)
7. Populates test data (FAS agreements, groups, users)
8. Creates service account for application LDAP binding
9. Grants service account read-only permissions

**Test Data Created:**
- 20 test users (all password: `password`)
- FAS agreement: FPCA
- FAS groups: developers, designers, elections, infra, QA, translators, ambassadors
- Users auto-assigned to groups based on FPCA signature
- Member managers (sponsors) for groups

### 3. Integration with Dev Environment

**Wired into `infra/envs/dev/main.tf`:**
- FreeIPA module instance in first public subnet
- `null_resource` to wait for SSH and automatically run Ansible
- Triggers on instance ID or playbook changes

**New Variables (`infra/envs/dev/variables.tf`):**
- `ssh_key_name`: EC2 key pair for instance access
- `ssh_private_key_path`: Path to private key for Ansible
- `freeipa_hostname`: FQDN (default: `ipa.astra-dev.test`)
- `freeipa_domain`: Domain (default: `astra-dev.test`)
- `freeipa_realm`: Kerberos realm (default: `ASTRA-DEV.TEST`)
- `freeipa_admin_password`: Admin password (default: `DevPassword123!`)
- `freeipa_dm_password`: Directory Manager password
- `freeipa_service_username`: Service account (default: `svc_astra`)
- `freeipa_service_password`: Service account password (default: `ServicePassword456!`)
- `freeipa_allowed_cidrs`: CIDRs for UI/SSH access

**Updated Application Connection Variables:**
- `freeipa_host`: Now points to `ipa.astra-dev.test` (was external demo)
- `freeipa_service_user`: Now `svc_astra` (was `admin`)

**New Outputs (`infra/envs/dev/outputs.tf`):**
- `freeipa_public_ip`: Public IP address
- `freeipa_private_ip`: Private IP address
- `freeipa_web_ui_url`: Web UI URL
- `freeipa_ldap_uri`: LDAP URI for apps
- `freeipa_admin_credentials`: Admin credentials (sensitive)
- `freeipa_service_credentials`: Service account credentials (sensitive)

## FAS Extensions Included

Based on `fedora-infra/freeipa-fas`, the following extensions are installed:

### Custom User Attributes
- `fasircnick`: IRC nicknames
- `faslocale`: User locale preference
- `fastimezone`: User timezone
- `fasstatusnote`: Account status note
- `fasgpgkeyid`: GPG key IDs

### Custom IPA Commands
- `fasagreement-add`: Create agreements (like FPCA)
- `fasagreement-add-user`: Sign user to agreement
- `fasagreement-add-group`: Link agreement to group
- `group-add-member-manager`: Add sponsors/managers
- `group-add(..., fasgroup=True)`: Create FAS-style groups

### Automember Rules
- Automatically adds users to `signed_FPCA` group when they sign FPCA
- Groups can require FPCA signature for membership

## DNS Considerations

**Current Setup:**
- FreeIPA runs its own DNS server for `astra-dev.test` domain
- Uses DNS forwarders: `8.8.8.8`, `8.8.4.4`
- `--no-host-dns` flag used (no reverse DNS zone setup required)

**Limitations:**
- Internal DNS only works from within AWS VPC
- External access requires `/etc/hosts` entries or private DNS zones
- For production, use Route53 private hosted zone

**Workaround for Dev:**
Add to `/etc/hosts` on local machine:
```
<FREEIPA_PUBLIC_IP>  ipa.astra-dev.test
```

## Usage

### Deploy FreeIPA

```bash
cd infra/envs/dev

# Ensure you have an SSH key pair
export TF_VAR_ssh_key_name="your-key-name"
export TF_VAR_ssh_private_key_path="~/.ssh/your-key.pem"

# Optional: Override passwords
export TF_VAR_freeipa_admin_password="YourAdminPass"
export TF_VAR_freeipa_service_password="YourServicePass"

terraform init
terraform plan
terraform apply
```

### Access FreeIPA

After deployment completes:

```bash
# Get connection details
terraform output freeipa_web_ui_url
terraform output freeipa_public_ip

# Add to /etc/hosts
echo "$(terraform output -raw freeipa_public_ip) ipa.astra-dev.test" | sudo tee -a /etc/hosts

# Access web UI
open https://ipa.astra-dev.test/
# Login: admin / DevPassword123! (or your override)

# SSH to IPA server
ssh -i ~/.ssh/your-key.pem fedora@$(terraform output -raw freeipa_public_ip)
```

### Application Connection

The Django app will automatically connect to FreeIPA using:
- **Host:** `ipa.astra-dev.test` (via VPC private IP)
- **Service User:** `svc_astra`
- **Service Password:** From Secrets Manager (populated from variable)
- **CA Cert:** Downloaded to `ansible/ipa_ca.crt` (upload to S3 or embed in image)

## What Was Copied from tiny-stage

**Directly Adapted:**
1. **User creation with FAS attributes** (`create_fas_test_data.py`)
2. **FAS agreement setup** (FPCA, automember rules)
3. **Group structure** (developers, designers, elections, etc.)
4. **Member manager functionality** (sponsors)

**Installation approach:** Based on tiny-stage IPA role logic but simplified for single-instance dev use

## What Was Intentionally Dropped

**Not Needed for Dev:**
- Multiple VMs (auth, tinystage, separate IPA server)
- Vagrant/libvirt-specific configuration
- Fedora Messaging setup
- FASJSON, Ipsilon, Noggin (separate services tiny-stage runs)
- Mail server (Sendria)
- Complex networking between multiple machines
- NTP configuration (using cloud provider time sync)
- Host DNS reverse zones (not needed for dev)
- Replication/high availability
- ansible-freeipa collection (using direct ipa-server-install)

## Required Assumptions

1. **AWS Region:** `eu-west-1` (or override via `aws_region`)
2. **VPC CIDR:** `10.20.0.0/16` (configurable)
3. **SSH Key:** You must have an EC2 key pair created
4. **Ansible:** Installed locally for Terraform to execute
5. **Python packages:** `python-freeipa`, `faker` installed on IPA server (playbook handles this)
6. **Instance Size:** `t3.medium` minimum (IPA is resource-intensive)
7. **Storage:** 30 GB for IPA data (certificates, LDAP, Kerberos database)

## Instance Sizing

**Dev Default:** `t3.small` (2 vCPU, 2 GB RAM)
- FreeIPA includes: LDAP, Kerberos KDC, DNS, Certificate Authority, Web UI
- Installation will be slower but functional for dev/testing
- Low user traffic makes this acceptable

**Production Recommended:** `t3.medium` or larger for better performance under load

## Cost Estimate (Dev)

- EC2 `t3.small`: ~$15/month (on-demand)
- EBS 30 GB: ~$3/month
- Elastic IP: Free while attached, $3.60/month if unattached
- Data transfer: Minimal for dev

**Total:** ~$18-22/month

**Cost Optimization:**
- Stop instance when not in use (keep EBS, pay ~$3/month)
- Use spot instances (not recommended for IPA as it needs stability)
- Skip Elastic IP (use dynamic public IP, update /etc/hosts as needed)

## Idempotency Notes

**Terraform:**
- Fully idempotent
- `null_resource` triggers only on instance recreation or playbook changes

**Ansible:**
- Most tasks use `register` and `changed_when` for proper idempotency
- IPA installation check: only runs `ipa-server-install` if `/etc/ipa/default.conf` missing
- FAS data population: uses `suppress(DuplicateEntry)` to handle reruns
- Service account creation: checks for "already exists" errors

**Rerunning:**
```bash
# Safe to rerun
terraform apply

# Manually rerun Ansible only
cd ../..
cd ansible
ansible-playbook -i ../infra/envs/dev/ipa_inventory.ini freeipa_setup.yml
```

## Troubleshooting

### SSH Connection Issues
```bash
# Check instance is running
terraform show | grep instance_state

# Test SSH manually
ssh -o StrictHostKeyChecking=no -i ~/.ssh/key.pem fedora@<PUBLIC_IP>

# Check security group allows SSH from your IP
aws ec2 describe-security-groups --group-ids <SG_ID>
```

### IPA Installation Failures
```bash
# SSH to instance
ssh -i ~/.ssh/key.pem fedora@<PUBLIC_IP>

# Check IPA logs
sudo journalctl -u ipa

# Check installation log
sudo cat /var/log/ipaserver-install.log
```

### FAS Extensions Not Loading
```bash
# Verify FAS package installed
python3 -c "import ipaserver.plugins.fasagreement"

# Check IPA can see the plugin
ipa fasagreement-help

# Restart IPA
sudo ipactl restart
```

### Ansible Hangs
- Check Ansible version: requires 2.9+
- Check Python on target: requires Python 3.x
- Increase timeout in `null_resource` if needed
- Run Ansible manually with `-vvv` for debug output

## Future Enhancements (Not Implemented)

**Not included for simplicity:**
- **Automated DNS via Route53:** Would require private hosted zone
- **TLS certificate automation:** Currently using self-signed IPA CA
- **Backup/restore automation:** Not critical for dev
- **Multi-AZ/HA setup:** Overkill for dev, needs 3+ replicas
- **Monitoring/alerting:** Dev doesn't need CloudWatch alarms
- **FASJSON/Noggin/Ipsilon:** Separate services, not required for basic LDAP/Kerberos

**If you need any of these, they're straightforward additions to the existing setup.**

## References

- **tiny-stage:** https://github.com/fedora-infra/tiny-stage
- **freeipa-fas:** https://github.com/fedora-infra/freeipa-fas
- **python-freeipa:** https://github.com/waldur/python-freeipa
- **FreeIPA docs:** https://freeipa.readthedocs.io/
