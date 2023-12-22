pipeline {
    agent {
        label 'jenkyns-host'
    }
    parameters {
        string(name: 'GIT_REPOSITORY', defaultValue: 'https://github.com/tribler/tribler.git', description: 'Git Repository')
        string(name: 'GIT_BRANCH', defaultValue: 'main', description: 'Git branch')
    }
    environment {
        SENTRY_URL = 'https://26d22e0fd6d14095b7eb496dccae6c79@sentry.tribler.org/7'
        LC_ALL = 'en_US.UTF-8'
        MACOS_ARTIFACTS = 'tribler/dist/*.dmg, tribler/dist/*.dmg.analysis.json'
        LINUX_ARTIFACTS = '**/debian/*.deb,**/debian/*.changes, **/*.analysis.json'
        WINDOWS_ARTIFACTS = 'tribler/dist/*.exe, tribler/dist/*.exe.analysis.json'
        BUILD_ARTIFACTS = '*.txt, *.txt.asc, *.deb, *.dmg, *.exe, *.changes, *.analysis.json'
    }
    stages {
        stage('Build binaries') {
            parallel {
                stage('Build MacOS') {
                    agent { label 'builder_macos' }
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

                stage('Build Ubuntu') {
                    agent { label 'builder_ubuntu' }
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

                            git describe --tags | python3 -c 'import sys; print(next(sys.stdin).lstrip("v"))' > .TriblerVersion
                            git rev-parse HEAD > .TriblerCommit

                            python3 ./build/update_version.py -r .
                            build/debian/makedist_debian.sh
                        '''
                    }
                    post {
                        success {
                            archiveArtifacts artifacts: env.LINUX_ARTIFACTS, fingerprint: true, allowEmptyArchive: true
                        }
                    }
                }

                stage('Build Windows 64bit') {
                    agent { label 'builder_win64' }
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

                stage('Build Windows 32bit') {
                    agent { label 'builder_win32' }
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
                            python3 ./build/win/replace_nsi.py -r .

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

        stage('Sign Artifacts') {
            agent { label 'artifact-signer' }
            steps {
                cleanWs()
                step([
                    $class: 'CopyArtifact',
                    filter: [env.LINUX_ARTIFACTS, env.WINDOWS_ARTIFACTS, env.MACOS_ARTIFACTS].join(','),
                    fingerprintArtifacts: true,
                    flatten: true,
                    optional: true,
                    projectName: env.JOB_NAME,
                    selector: [$class: 'SpecificBuildSelector', buildNumber: env.BUILD_NUMBER]
                ])
                sh '''
                    #!/bin/bash

                    ls -r

                    md5sum *.exe *.dmg *.deb > MD5.txt
                    sha1sum *.exe *.dmg *.deb > SHA1.txt
                    sha256sum *.exe *.dmg *.deb > SHA256.txt

                    # Sign the build hash
                    gpg2 --no-tty -u 47CDE6C0 --pinentry-mode loopback --passphrase-file $HOME/tribler_signing_pw.txt --output MD5.txt.asc --detach-sig MD5.txt
                    gpg2 --no-tty -u 47CDE6C0 --pinentry-mode loopback --passphrase-file $HOME/tribler_signing_pw.txt --output SHA1.txt.asc --detach-sig SHA1.txt
                    gpg2 --no-tty -u 47CDE6C0 --pinentry-mode loopback --passphrase-file $HOME/tribler_signing_pw.txt --output SHA256.txt.asc --detach-sig SHA256.txt

                    # Verify the signature
                    gpg2 --verify MD5.txt.asc MD5.txt
                    gpg2 --verify SHA1.txt.asc SHA1.txt
                    gpg2 --verify SHA256.txt.asc SHA256.txt
                '''
            }
            post {
                success {
                    archiveArtifacts artifacts: env.BUILD_ARTIFACTS, fingerprint: true, allowEmptyArchive: true
                }
            }
        }
    }
}