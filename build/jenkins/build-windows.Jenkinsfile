def buildTriblerOnWindows(archTypeArgument) {
    cleanWs()
    checkout scm: [
        $class: 'GitSCM',
        branches: [[name: params.GIT_BRANCH]],
        clean: true,
        userRemoteConfigs: [[url: params.GIT_REPOSITORY]],
        extensions: [[$class: 'RelativeTargetDirectory', relativeTargetDir: 'tribler']]
    ]
    script{
        bat """
            cd tribler

            git describe --tags | python -c "import sys; print(next(sys.stdin).lstrip('v'))" > .TriblerVersion
            git rev-parse HEAD > .TriblerCommit

            python3 ./build/update_version.py -r .
            python3 ./build/win/replace_nsi.py -r . %archTypeArgument%

            build\\win\\makedist_win.bat
        """
    }
}

pipeline {
    agent { label 'builder_win64' }
    parameters {
        string(name: 'GIT_REPOSITORY', defaultValue: 'https://github.com/tribler/tribler.git', description: 'Git Repository')
        string(name: 'GIT_BRANCH', defaultValue: 'main', description: 'Git branch')
        booleanParam(name: 'BUILD_WIN32', defaultValue: true, description: 'Should build Win32 version?')
        booleanParam(name: 'BUILD_WIN64', defaultValue: true, description: 'Should build Win64 version?')
    }
    environment {
        SENTRY_URL = 'https://26d22e0fd6d14095b7eb496dccae6c79@sentry.tribler.org/7'
        WINDOWS_ARTIFACTS = 'tribler/dist/*.exe, tribler/dist/*.exe.analysis.json'
    }
    stages {
        stage('Check options'){
            steps {
                script {
                    if (params.BUILD_WIN32 == false && params.BUILD_WIN64 == false) {
                        error('Both BUILD_WIN32 and BUILD_WIN64 are false. Please enable at least one of them.')
                    }
                }
            }
        }
        stage('Build binaries') {
            parallel {
                stage('Build Win64') {
                    when {
                        expression {
                            params.BUILD_WIN64 == true
                        }
                    }
                    steps {
                        buildTriblerOnWindows("--architecture x64")
                    }
                    post {
                        success {
                            archiveArtifacts artifacts: env.WINDOWS_ARTIFACTS, fingerprint: true, allowEmptyArchive: true
                        }
                    }
                }
                stage('Build Win32') {
                    agent { label 'builder_win32' }
                    when {
                        expression {
                            params.BUILD_WIN32 == true
                        }
                    }
                    steps {
                        buildTriblerOnWindows("")
                    }
                    post {
                        success {
                            archiveArtifacts artifacts: env.WINDOWS_ARTIFACTS, fingerprint: true, allowEmptyArchive: true
                        }
                    }
                }
            }
        }
    }
}
