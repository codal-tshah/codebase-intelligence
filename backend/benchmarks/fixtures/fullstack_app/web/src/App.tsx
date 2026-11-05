import { BrowserRouter, Route, Routes } from "react-router-dom";
import { ItemList } from "@/components/ItemList";
import ItemPage from "./pages/ItemPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<ItemList />} />
        <Route path="/items/:id" element={<ItemPage />} />
      </Routes>
    </BrowserRouter>
  );
}
