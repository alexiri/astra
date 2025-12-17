# AGENTS instructions

## Test tips
- You don't need to restart the web container after code changes; it refreshes automatically.
- You can smoke-test Django with: `podman-compose exec -T web python manage.py check`
- Stop and restart everything: `podman-compose down && podman-compose up -d --build`. NEVER RUN `podman-compose down -v` as that will delete your database!
