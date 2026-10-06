import { Link } from "react-router-dom";
import { Empty } from "../design-system/UI";

export default function NotFound() {
  return (
    <div className="container">
      <Empty title="Page not found" hint="The page you were looking for does not exist." action={<Link to="/" className="btn btn-primary">Go home</Link>} />
    </div>
  );
}
