pipeline {
    agent { label 'builder_win64' }
    parameters {
        string(name: 'GIT_REPOSITORY', defaultValue: 'https://github.com/tribler/tribler.git', description: 'Git Repository')
        string(name: 'GIT_BRANCH', defaultValue: 'main', description: 'Git branch')
    }
    environment {
        SENTRY_URL = 'https://26d22e0fd6d14095b7eb496dccae6c79@sentry.tribler.org/7'
        WINDOWS_ARTIFACTS = 'tribler/dist/*.exe, tribler/dist/*.exe.analysis.json'
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
                // Execute Windows batch commands
                bat """
                    cd tribler

                    git describe --tags | python -c "import sys; print(next(sys.stdin).lstrip('v'))" > .TriblerVersion
                    git rev-parse HEAD > .TriblerCommit

                    python3 ./build/update_version.py -r .
                    python3 ./build/win/replace_nsi.py -r . --architecture x64

                    build\\win\\makedist_win.bat
                """
            }
            post {
                success {
                    archiveArtifacts artifacts: env.WINDOWS_ARTIFACTS, fingerprint: true, allowEmptyArchive: true
                }
            }
        }
    }
}
