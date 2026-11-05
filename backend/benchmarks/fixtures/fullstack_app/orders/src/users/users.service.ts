import { Injectable } from "@nestjs/common";

@Injectable()
export class UsersService {
  findAll() {
    return [];
  }
  findOne(id: string) {
    return { id };
  }
}
