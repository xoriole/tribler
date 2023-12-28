pipeline {
    agent { label 'builder_ubuntu' }
    parameters {
        string(name: 'GIT_REPOSITORY', defaultValue: 'https://github.com/tribler/tribler.git', description: 'Git Repository')
        string(name: 'GIT_BRANCH', defaultValue: 'main', description: 'Git branch')
        string(name: 'UTILS_GIT_REPOSITORY', defaultValue: 'https://github.com/Tribler/tribler-utils.git', description: 'Tribler utils git Repository')
        string(name: 'UTILS_GIT_BRANCH', defaultValue: 'master', description: 'Tribler utils git branch')
        booleanParam(name: 'VIRUS_CHECK', defaultValue: false, description: 'Check for malware reports from VirusTotal')
    }
    environment {
        SENTRY_URL = 'https://26d22e0fd6d14095b7eb496dccae6c79@sentry.tribler.org/7'
        LINUX_ARTIFACTS = '**/debian/*.deb,**/debian/*.changes, **/*.analysis.json'
    }
    stages {
        stage('Build binaries') {
            steps {
                cleanWs()
                checkout scm: [
                    $class: 'GitSCM',
                    branches: [[name: params.GIT_BRANCH]],
                    clean: true,
                    userRemoteConfigs: [[url: params.GIT_REPOSITORY]],
                    extensions: [[$class: 'RelativeTargetDirectory', relativeTargetDir: 'tribler']]
                ]
                script {
                    sh '''
                        #!/bin/bash
                        cd tribler

                        git describe --tags | python3 -c 'import sys; print(next(sys.stdin).lstrip("v"))' > .TriblerVersion
                        git rev-parse HEAD > .TriblerCommit

                        python3 ./build/update_version.py -r .
                        build/debian/makedist_debian.sh
                    '''

                    if(params.VIRUS_CHECK){
                        checkout scm: [
                            $class: 'GitSCM',
                            branches: [[name: params.UTILS_GIT_BRANCH]],
                            clean: true,
                            userRemoteConfigs: [[url: params.UTILS_GIT_REPOSITORY]],
                            extensions: []
                        ]
                        sh '''
                            #!/bin/bash
                            export VENV=/home/tribler/venv
                            echo Checking for malware executing: ${VIRUS_CHECK}
                            source /home/tribler/venv/bin/activate
                            pip install requests
                            python3 virustotal_check.py
                            deactivate
                        '''
                    }
                }
            }
            post {
                success {
                    archiveArtifacts artifacts: env.LINUX_ARTIFACTS, fingerprint: true, allowEmptyArchive: true
                }
            }
        }
        stage('Virus Check') {
            when {
                expression {
                    return false
                }
            }
            steps {
                checkout scm: [
                    $class: 'GitSCM',
                    branches: [[name: params.UTILS_GIT_BRANCH]],
                    clean: true,
                    userRemoteConfigs: [[url: params.UTILS_GIT_REPOSITORY]],
                    extensions: []
                ]
                sh '''
                    #!/bin/bash
                    export VENV=/home/tribler/venv
                    echo Checking for malware executing: ${VIRUS_CHECK}
                    source /home/tribler/venv/bin/activate
                    pip install requests
                    python3 virustotal_check.py
                    deactivate
                '''
            }
        }
    }

}
