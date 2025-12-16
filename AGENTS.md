# AGENTS instructions

## Test tips
- You can run this to test things look sane: `podman-compose exec -T web python manage.py check`
- Stop and restart everything: `podman-compose down && podman-compose up -d --build`. NEVER RUN `podman-compose down -v` as that will delete your database!
