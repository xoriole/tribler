def checkForMalware(archTypeArgument) {
    step([
        $class: 'CopyArtifact',
        filter: '*.deb',
        fingerprintArtifacts: true,
        flatten: true,
        optional: true,
        projectName: env.ARTIFACT_JOB_NAME,
        selector: lastSuccessful()
    ])
    sh '''
        ls -r
    '''
    script {
        sh '''
            #!/bin/bash
            export VENV=/home/tribler/venv
            echo Checking for malware executing: ${VIRUS_CHECK}
            . /home/tribler/venv/bin/activate
            pip install requests
            python3 virustotal_check.py
            deactivate
        '''
    }
}

pipeline {
    agent { label 'builder_ubuntu' }
    parameters {
        string(name: 'UTILS_GIT_REPOSITORY', defaultValue: 'https://github.com/Tribler/tribler-utils.git', description: 'Tribler utils git Repository')
        string(name: 'UTILS_GIT_BRANCH', defaultValue: 'master', description: 'Tribler utils git branch')
    }
    environment {
        LINUX_ARTIFACTS = '**/debian/*.deb,**/debian/*.changes, **/*.analysis.json'
        ARTIFACT_JOB_NAME = 'Tribler/Build/Build-Ubuntu'
        INSTALLER_FILE_SUFFIX = '.deb'
        VIRUSTOTAL_API_KEY = '276fd116e4c4180caaa7831981d0817accf8df488c1201d595f85630ae73a79a'
    }
    stages {
        stage('Check for malware') {
            steps {
                cleanWs()
                checkout scm: [
                    $class: 'GitSCM',
                    branches: [[name: params.UTILS_GIT_BRANCH]],
                    clean: true,
                    userRemoteConfigs: [[url: params.UTILS_GIT_REPOSITORY]],
                    extensions: []
                ]
                step([
                    $class: 'CopyArtifact',
                    filter: env.LINUX_ARTIFACTS,
                    fingerprintArtifacts: true,
                    flatten: true,
                    optional: true,
                    projectName: env.ARTIFACT_JOB_NAME,
                    selector: lastSuccessful()
                ])
                sh '''
                    ls -r
                '''
                script {
                    sh '''
                        #!/bin/bash
                        export VENV=/home/tribler/venv
                        echo Checking for malware executing: ${VIRUS_CHECK}
                        . /home/tribler/venv/bin/activate
                        pip install requests
                        python3 virustotal_check.py
                        deactivate
                    '''
                }
            }
            post {
                success {
                    archiveArtifacts artifacts: env.LINUX_ARTIFACTS, fingerprint: true, allowEmptyArchive: true
                }
            }
        }
    }
}
