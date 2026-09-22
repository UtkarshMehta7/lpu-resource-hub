import { createBrowserRouter } from "react-router-dom";

import { AdminUsersPage } from "@/features/admin/AdminUsersPage";
import { DirectoryPage } from "@/features/directory/DirectoryPage";
import { ResearcherDetailPage } from "@/features/directory/ResearcherDetailPage";
import { StudentsPage } from "@/features/directory/StudentsPage";
import { AccountPage } from "@/features/auth/AccountPage";
import { LoginPage } from "@/features/auth/LoginPage";
import { ProtectedRoute } from "@/features/auth/ProtectedRoute";
import { RegisterPage } from "@/features/auth/RegisterPage";
import { RoleRoute } from "@/features/auth/RoleRoute";
import { HomePage } from "@/features/home/HomePage";
import { NotFoundPage } from "@/features/home/NotFoundPage";
import { OnboardingPage } from "@/features/onboarding/OnboardingPage";
import { ProfilePage } from "@/features/profiles/ProfilePage";
import { VerificationQueuePage } from "@/features/researchers/VerificationQueuePage";

import { AppLayout } from "./layouts/AppLayout";

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      { index: true, element: <HomePage /> },
      { path: "login", element: <LoginPage /> },
      { path: "register", element: <RegisterPage /> },
      {
        element: <ProtectedRoute />,
        children: [
          { path: "account", element: <AccountPage /> },
          { path: "researchers", element: <DirectoryPage /> },
          { path: "researchers/:userId", element: <ResearcherDetailPage /> },
          { path: "onboarding", element: <OnboardingPage /> },
          { path: "profile", element: <ProfilePage /> },
          {
            element: <RoleRoute allow={["research_coordinator", "admin"]} />,
            children: [
              { path: "coordinator/verification-queue", element: <VerificationQueuePage /> },
            ],
          },
          {
            element: <RoleRoute allow={["faculty", "research_coordinator", "admin"]} />,
            children: [{ path: "students", element: <StudentsPage /> }],
          },
          {
            element: <RoleRoute allow={["admin"]} />,
            children: [{ path: "admin/users", element: <AdminUsersPage /> }],
          },
        ],
      },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);
