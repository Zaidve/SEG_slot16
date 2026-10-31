# Roles are Django Groups, created in migration 0003_create_roles.
# A logged-in user with no group is a Reader.
SUPER_ADMIN = 'Super Admin'
CONTENT_MANAGER = 'Content Manager'
MODERATOR = 'Moderator'
DATA_SEO = 'Data & SEO'

STAFF_ROLES = [SUPER_ADMIN, CONTENT_MANAGER, MODERATOR, DATA_SEO]
