# WeChat Removal Tool Layout

Structure

- config/
  - computer_windows.yaml
  - model.yaml
- runtime/
  - computer_session.py
  - model_session.py
- modules/
  - group_classifier.py
  - unread_scanner.py
  - message_reader.py
  - suspicious_detector.py
  - removal_precheck.py
  - human_confirmation.py
  - removal_executor.py
  - task_types.py
- workflow/
  - run_wechat_removal.py
- artifacts/
  - captures/
  - logs/
- vendor/
  - agent/ (vendored CUA agent)
  - computer/ (vendored CUA computer)
  - computer-server/ (vendored CUA computer server)
  - core/ (vendored CUA core)
