# ============================================================
# setup-jenkins.ps1
# Run this after recreating the Jenkins container to restore
# Docker CLI, kubectl, and kubeconfig access.
# ============================================================

Write-Host "Installing Docker CLI inside Jenkins container..."
docker exec -u root jenkins bash -c "apt-get update && apt-get install -y docker.io"

Write-Host "Fixing Docker socket permissions..."
docker exec -u root jenkins chmod 666 /var/run/docker.sock

Write-Host "Installing kubectl inside Jenkins container..."
docker exec -u root jenkins bash -c "curl -LO https://dl.k8s.io/release/v1.33.0/bin/linux/amd64/kubectl && chmod +x kubectl && mv kubectl /usr/local/bin/kubectl"

Write-Host "Copying kubeconfig into Jenkins container..."
docker exec -u root jenkins bash -c "mkdir -p /root/.kube"
docker cp C:\Users\GAMING\.kube\config jenkins:/root/.kube/config

Write-Host "Patching kubeconfig to use host.docker.internal..."
docker exec -u root jenkins sed -i 's/127.0.0.1/host.docker.internal/g' /root/.kube/config

Write-Host "Disabling TLS verification for local cluster..."
docker exec -u root jenkins kubectl config set-cluster docker-desktop --insecure-skip-tls-verify=true

Write-Host "Copying kubeconfig to jenkins user home..."
docker exec -u root jenkins bash -c "mkdir -p /var/jenkins_home/.kube && cp /root/.kube/config /var/jenkins_home/.kube/config && chown -R jenkins:jenkins /var/jenkins_home/.kube"

Write-Host "Verifying Docker..."
docker exec jenkins docker --version

Write-Host "Verifying kubectl as jenkins user..."
docker exec jenkins kubectl get nodes

Write-Host "Done. Jenkins is ready."
