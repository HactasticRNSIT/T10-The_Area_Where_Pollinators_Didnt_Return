
git remote add personal https://github.com/sridharjrao07-bit/polynexus.git

# Create and push backend feature branch
git checkout -b feature/backend-integration
git add backend/config.py backend/scorer.py backend/zone_weights.yaml
git commit -m "feat(backend): add zone-specific weights and thresholds"
git add backend/data_fetcher.py backend/api.py backend/ai_analyzer.py backend/anomaly_detector.py backend/main.py backend/mock_data.py
git commit -m "feat(backend): integrate real agricultural data APIs"

# Create and push frontend feature branch
git checkout -b feature/frontend-ux
git add frontend/index.html frontend/style.css
git commit -m "feat(frontend): implement glassmorphism UI redesign"
git add frontend/app.js
git commit -m "fix(frontend): improve search UX and add loading animations"

# Create and push chore branch
git checkout -b chore/scripts-and-tests
git add backend/test_accuracy.py backend/test_output.json test_results_accuracy.json
git commit -m "test: add data accuracy verification scripts"
git add update_app.py update_app_declutter.py update_app_str.py update_ui.py backend/fix_polygon.py backend/fix_polygon2.py
git commit -m "chore: add maintenance and update scripts"

# Commit any remaining files (like deleted .env.example)
git add -A
git commit -m "chore: cleanup remaining files"

# Push all branches to the new remote
git push personal main
git push personal feature/backend-integration
git push personal feature/frontend-ux
git push personal chore/scripts-and-tests

# Also update the personal main branch to include all these changes
git push personal chore/scripts-and-tests:main

