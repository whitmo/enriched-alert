# Alertmanager values template for kube-prometheus-stack.
# DEPLOY_NAMESPACE is replaced by the Makefile with the actual TEST_NS value.

alertmanager:
  config:
    route:
      receiver: 'ai-agent-webhook'
      group_by: ['alertname', 'slo_name']
      group_wait: 10s
      group_interval: 30s
      repeat_interval: 1h
    receivers:
      - name: 'ai-agent-webhook'
        webhook_configs:
          - url: 'http://ai-agent.DEPLOY_NAMESPACE.svc.cluster.local:8080/alert'
            send_resolved: true
