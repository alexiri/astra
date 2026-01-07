# Application module
#
# AWS has an “Application” view in the console (Systems Manager → Application Manager / Resource Groups)
# that is powered by Resource Groups.
#
# This module creates a per-environment Resource Group that automatically includes
# all resources tagged with:
#   app = <app_name>
#   env = <environment>
#
# No explicit per-resource association is needed; tagging is the “assignment”.

resource "aws_resourcegroups_group" "this" {
  name = "${var.app_name}-${var.environment}"

  resource_query {
    type = "TAG_FILTERS_1_0"

    query = jsonencode({
      ResourceTypeFilters = ["AWS::AllSupported"]
      TagFilters = [
        {
          Key    = "app"
          Values = [var.app_name]
        },
        {
          Key    = "env"
          Values = [var.environment]
        }
      ]
    })
  }

  tags = merge(var.tags, {
    Name = "${var.app_name}-${var.environment}"
    app  = var.app_name
    env  = var.environment
  })
}

resource "aws_servicecatalogappregistry_application" "this" {
  count = var.enable_appregistry ? 1 : 0

  name        = "${var.app_name}-${var.environment}"
  description = var.description

  tags = merge(var.tags, {
    Name = "${var.app_name}-${var.environment}"
    app  = var.app_name
    env  = var.environment
  })
}
