# AGENTS instructions

- If you're not entirely sure how to use a library or module, look it up. Find the source code,
  docs, whatever. It's ok to ask the user for a link to the documentation or code if needed.
- Add clean code with sensible comments. Consider what you're implementing and the context, as well
  as how you can generalize functions to reduce code duplication and sources of bugs.
- Do Test-Driven development: Add tests before you implement a new feature, make sure they cover all the
  failure scenarios and that they really *do* fail. Then implement the new feature and make sure your tests pass.

## Test tips
- You don't need to restart the web container after code changes; it refreshes automatically.
- This is python, you don't need to compile the code.
- You can smoke-test Django with: `podman-compose exec -T web python manage.py check`
- You can run more tests with: `podman-compose exec -T web python manage.py test`
- Stop and restart everything: `podman-compose down && podman-compose up -d --build`. NEVER RUN `podman-compose down -v` as that will delete your database!
