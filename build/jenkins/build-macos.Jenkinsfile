pipeline {
    agent { label 'builder_macos' }
    parameters {
        string(name: 'GIT_REPOSITORY', defaultValue: 'https://github.com/tribler/tribler.git', description: 'Git Repository')
        string(name: 'GIT_BRANCH', defaultValue: 'main', description: 'Git branch')
    }
    environment {
        SENTRY_URL = 'https://26d22e0fd6d14095b7eb496dccae6c79@sentry.tribler.org/7'
        MACOS_ARTIFACTS = 'tribler/dist/*.dmg, tribler/dist/*.dmg.analysis.json'
    }
    stages {
        stage('Build MacOS') {
            steps {
                cleanWs()
                checkout scm: [
                    $class: 'GitSCM',
                    branches: [[name: params.GIT_BRANCH]],
                    clean: true,
                    userRemoteConfigs: [[url: params.GIT_REPOSITORY]],
                    extensions: [[$class: 'RelativeTargetDirectory', relativeTargetDir: 'tribler']]
                ]
                sh '''
                    #!/bin/bash
                    cd tribler

                    git describe --tags | python -c "import sys; print(next(sys.stdin).lstrip('v'))" > .TriblerVersion
                    git rev-parse HEAD > .TriblerCommit
                    export TRIBLER_VERSION=$(head -n 1 .TriblerVersion)

                    python3 ./build/update_version.py -r . || python3 build/update_version_from_git.py
                    ./build/mac/makedist_macos.sh
                '''
            }
            post {
                success {
                    archiveArtifacts artifacts: env.MACOS_ARTIFACTS, fingerprint: true, allowEmptyArchive: true
                }
            }
        }
    }
}
