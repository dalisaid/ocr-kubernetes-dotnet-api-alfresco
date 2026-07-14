# start-ports.ps1
Start-Process powershell { kubectl port-forward svc/grafana 30000:80 -n ocr-lab }
Start-Process powershell { kubectl port-forward svc/gateway 30010:8000 -n ocr-lab }
Start-Process powershell { kubectl port-forward svc/prometheus-server 30090:80 -n ocr-lab }
Start-Process powershell { kubectl port-forward svc/rabbitmq 15672:15672 -n ocr-lab }