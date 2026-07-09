resource "aws_ecs_service" "api" {
  name            = "${var.project_name}-api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  # Slow first-start apps (e.g. cold npm/JIT warmup) shouldn't get killed by
  # an early failing health check before they're actually ready.
  health_check_grace_period_seconds = 60

  # Lets `aws ecs execute-command` open a shell in the running task — used to
  # load the DB schema (see README) since the RDS instance isn't reachable
  # from outside the VPC by design.
  enable_execute_command = true

  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.ecs_task.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = var.container_port
  }

  depends_on = [aws_lb_listener.http]

  tags = {
    Name = "${var.project_name}-api-service"
  }
}
