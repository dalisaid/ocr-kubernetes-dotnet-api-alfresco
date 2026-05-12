using MongoDB.Driver;
using OnboardingApi.Models;

namespace OnboardingApi.Services;

public class MongoService
{
    private readonly IMongoCollection<Client> _collection;
    
    private readonly IConfiguration _config; 
 

    public MongoService(IConfiguration config)
    
    {
        _config = config;
        var client = new MongoClient(config["Mongo:ConnectionString"]);
        var database = client.GetDatabase(config["Mongo:DatabaseName"]);
        _collection = database.GetCollection<Client>("Clients");
    }

    public async Task Save(Client req)
    {
        await _collection.InsertOneAsync(req);
    }
}