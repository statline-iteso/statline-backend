-- Cognito sign-in (infra D-47): users signed in through Cognito have no local password, and are
-- linked to their Cognito user by its sub.
ALTER TABLE "usuario" ALTER COLUMN "password_hash" DROP NOT NULL;
ALTER TABLE "usuario" ADD COLUMN "cognito_sub" TEXT;
CREATE UNIQUE INDEX "usuario_cognito_sub_key" ON "usuario"("cognito_sub");
