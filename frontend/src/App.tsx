/*
  Routes.

  One place listing every screen in the app and the URL it lives at.
  Add a route here when you add a page.
*/

import { Routes, Route } from "react-router-dom";

import Home from "./pages/Home";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
    </Routes>
  );
}
