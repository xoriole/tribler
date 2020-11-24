docker volume rm --force experiment_state_directory
docker stack deploy -c docker-compose.yml experiment
