import { createBrowserRouter } from "react-router-dom";

import { AccountPage } from "@/features/auth/AccountPage";
import { LoginPage } from "@/features/auth/LoginPage";
import { ProtectedRoute } from "@/features/auth/ProtectedRoute";
import { RegisterPage } from "@/features/auth/RegisterPage";
import { HomePage } from "@/features/home/HomePage";
import { NotFoundPage } from "@/features/home/NotFoundPage";

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
        children: [{ path: "account", element: <AccountPage /> }],
      },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);
