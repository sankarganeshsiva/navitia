#pragma once
#include "type/type.h"
#include "type/data.h"
#include "routing.h"
#include "utils/timer.h"
#include <unordered_map>
#include "boost/dynamic_bitset.hpp"
#include <google/dense_hash_map>
#include "routing/raptor_utils.h"
#include "routing/dataraptor.h"

namespace navitia { namespace routing { namespace raptor{

typedef std::pair<navitia::type::idx_t, int> pair_idx_int;
typedef std::vector<int> queue_t;
typedef std::vector<map_int_pint_t> map_retour_t;
typedef std::vector<pair_int> vector_pairint;
typedef std::pair<navitia::type::idx_t, type_retour> idx_retour;
typedef std::vector<idx_retour> vector_idxretour;
typedef std::pair<navitia::type::idx_t, double> idx_distance;
typedef std::vector<idx_distance> vec_idx_distance;


struct RAPTOR : public AbstractRouter
{
    const navitia::type::Data & data;

    //Données modifiées pendant le calcul
    map_retour_t retour;
    map_int_pint_t best;
    best_dest b_dest;
    unsigned int count;
    boost::dynamic_bitset<> marked_sp;
    boost::dynamic_bitset<> vp_valides;
    queue_t Q;

    //Constructeur
    RAPTOR(const navitia::type::Data &data) :  data(data), best(data.pt_data.stop_points.size()), marked_sp(data.pt_data.stop_points.size()), vp_valides(data.pt_data.validity_patterns.size()), Q(data.dataRaptor.routes.size()) {
        retour.assign(20, data.dataRaptor.retour_constant);
    }


    std::vector<Path> compute(idx_t departure_idx, idx_t destination_idx, int departure_hour, int departure_day, senscompute sens = partirapres);

    Path makeBestPath(map_retour_t &retour, map_int_pint_t &best, vector_idxretour departs, unsigned int destination_idx, unsigned int count);
    Path makeBestPathreverse(map_retour_t &retour, map_int_pint_t &best, vector_idxretour departs, unsigned int destination_idx, unsigned int count);
    std::vector<Path> makePathes(map_retour_t &retour, map_int_pint_t &best, vector_idxretour departs, best_dest &b_dest, unsigned int count);
    std::vector<Path> makePathesreverse(map_retour_t &retour, map_int_pint_t &best, vector_idxretour departs, best_dest &b_dest, unsigned int count);

    /*std::vector<Path> compute_all(vec_idx_distance departures, vec_idx_distance targets, int departure_hour, int departure_day, senscompute sens);*/
    std::vector<Path> compute_all(navitia::type::EntryPoint departure, navitia::type::EntryPoint destination, int departure_hour, int departure_day, senscompute sens);
    std::vector<Path> compute_reverse_all(vector_idxretour departs, vector_idxretour destinations);
    std::vector<Path> compute_all(vector_idxretour departs, vector_idxretour destinations);


    void boucleRAPTOR(const std::vector<unsigned int> &marked_stop);
    Path makePath(map_retour_t &retour, map_int_pint_t &best, vector_idxretour departs, unsigned int destination_idx, unsigned int countb, bool reverse = false);
    void marcheapied();
    void setVPValides(const std::vector<unsigned int> &marked_stop);
    void make_queue();
    int earliest_trip(const dataRAPTOR::Route_t &route, unsigned int order, DateTime dt) const;

    void boucleRAPTORreverse(std::vector<unsigned int> &marked_stop);
    Path makePathreverse(map_retour_t &retour, map_int_pint_t &best, vector_idxretour departs, unsigned int destination_idx, unsigned int countb);
    void marcheapiedreverse();
    void setVPValidesreverse(std::vector<unsigned int> &marked_stop);
    void make_queuereverse();
    int tardiest_trip(const dataRAPTOR::Route_t &route, unsigned int order, DateTime dt) const;


    vector_idxretour trouverGeo(const type::GeographicalCoord & departure, const double radius_depart,  const int departure_hour, const int departure_day) const;

};



}}}
