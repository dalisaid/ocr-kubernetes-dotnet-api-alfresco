pipeline {
    agent any

    environment {
        DOCKER_USER = 'dalisaid'
    }

    stages {

        stage('Build Images') {
            steps {
                sh '''
                    docker build -t ${DOCKER_USER}/ocr-gateway:latest ./ocr-lab/gateway
                    docker build -t ${DOCKER_USER}/ocr-tesseract:latest ./ocr-lab/engines/tesseract
                    # docker build -t ${DOCKER_USER}/ocr-easyocr:latest ./ocr-lab/engines/easyocr
                    # docker build -t ${DOCKER_USER}/ocr-paddle:latest ./ocr-lab/engines/paddle
                '''
            }
        }

        stage('Push Images') {
            steps {
                withCredentials([usernamePassword(
                    credentialsId: 'dockerhub-credentials',
                    usernameVariable: 'DOCKER_USER',
                    passwordVariable: 'DOCKER_PASS'
                )]) {
                    sh '''
                        echo "$DOCKER_PASS" | docker login -u "$DOCKER_USER" --password-stdin
                        docker push ${DOCKER_USER}/ocr-gateway:latest
                        docker push ${DOCKER_USER}/ocr-tesseract:latest
                        # docker push ${DOCKER_USER}/ocr-easyocr:latest
                        # docker push ${DOCKER_USER}/ocr-paddle:latest
                        docker logout
                    '''
                }
            }
        }

        stage('Deploy to Kubernetes') {
            steps {
                sh '''
                    kubectl apply -f ocr-lab/k8s/gateway.yaml -n ocr-lab
                    kubectl apply -f ocr-lab/k8s/engine-tesseract.yaml -n ocr-lab
                    # kubectl apply -f ocr-lab/k8s/engine-easyocr.yaml -n ocr-lab
                    # kubectl apply -f ocr-lab/k8s/engine-paddle.yaml -n ocr-lab
                    # kubectl apply -f ocr-lab/monitoring/dashboard.yaml -n ocr-lab
                    
                    kubectl rollout restart deployment/gateway -n ocr-lab
                    kubectl rollout restart deployment/engine-tesseract -n ocr-lab
                    # kubectl rollout restart deployment/engine-easyocr -n ocr-lab
                    # kubectl rollout restart deployment/engine-paddle -n ocr-lab
                    kubectl rollout status deployment/gateway -n ocr-lab --timeout=180s
                    kubectl rollout status deployment/engine-tesseract -n ocr-lab --timeout=180s
                    # kubectl rollout status deployment/engine-easyocr -n ocr-lab --timeout=180s
                    # kubectl rollout status deployment/engine-paddle -n ocr-lab --timeout=180s
                '''
            }
        }

    }

    post {
        success {
            echo 'Pipeline completed successfully.'
        }
        failure {
            echo 'Pipeline failed.'
        }
        always {
            cleanWs()
        }
    }
}
